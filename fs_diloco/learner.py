"""Filesystem-backed Decoupled DiLoCo learner."""

from __future__ import annotations

import argparse
import math
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any

import torch

from .atomic_io import atomic_write_json, file_size, safe_read_json, sha256_file
from .config import Config, resolve_config
from .constants import FORMAT_VERSION, LEARNER_STATUS_ACTIVE, LEARNER_STATUS_STOPPED, learner_index_from_id
from .failure_sim import maybe_crash, maybe_sleep_jitter, should_skip_upload
from .hf_data import Batch, build_batch_iterator
from .hf_model import choose_device, load_causal_lm_and_tokenizer
from .logging_utils import JsonlLogger, log_uncaught_exception
from .metrics import LEARNER_METRIC_FIELDS, UPDATE_MANIFEST_FIELDS, append_csv_row
from .param_index import (
    build_param_index,
    flatten_trainable_params,
    load_flat_into_model,
    load_param_index,
    validate_compatible_index,
)
from .paths import RunPaths, prepare_run_dirs
from .tensor_codec import dtype_from_name, load_global_weights_flat, save_update_vector


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--shared-root")
    parser.add_argument("--learner-id", required=True)
    parser.add_argument("--num-learners", type=int)
    return parser.parse_args(argv)


def write_heartbeat(
    *,
    paths: RunPaths,
    config: Config,
    learner_id: str,
    status: str,
    phase: str,
    last_loaded_global_version: int,
    last_local_step: int,
    last_update_id: str | None,
    tokens_per_sec: float | None = None,
) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "run_id": config.run.run_id,
        "learner_id": learner_id,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "timestamp": time.time(),
        "status": status,
        "phase": phase,
        "last_loaded_global_version": last_loaded_global_version,
        "last_local_step": last_local_step,
        "last_update_id": last_update_id,
        "tokens_per_sec": tokens_per_sec,
    }
    atomic_write_json(paths.heartbeats / f"{learner_id}.json", payload)


def wait_for_json(path: Path, *, timeout_seconds: float = 1800.0, poll_seconds: float = 1.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = safe_read_json(path)
        if payload is not None:
            return payload
        time.sleep(poll_seconds)
    raise TimeoutError(f"timed out waiting for {path}")


def read_latest_if_newer(paths: RunPaths, last_loaded_global_version: int) -> dict[str, Any] | None:
    payload = safe_read_json(paths.latest_json)
    if payload is None:
        return None
    if int(payload.get("version", -1)) <= last_loaded_global_version:
        return None
    return payload


def stop_requested(paths: RunPaths, local_step: int, config: Config) -> bool:
    if config.training.max_local_steps is not None and local_step >= config.training.max_local_steps:
        return True
    return paths.stop_json.exists()


def build_inner_optimizer_and_scheduler(
    model: torch.nn.Module,
    config: Config,
) -> tuple[torch.optim.Optimizer, torch.optim.lr_scheduler.LRScheduler | None]:
    name = config.inner_optimizer.name.lower()
    if name != "adamw":
        raise ValueError(f"unsupported inner optimizer: {config.inner_optimizer.name}")
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.inner_optimizer.lr,
        betas=tuple(config.inner_optimizer.betas),
        eps=config.inner_optimizer.eps,
        weight_decay=config.inner_optimizer.weight_decay,
    )
    if config.inner_optimizer.scheduler == "none":
        return optimizer, None

    def lr_lambda(step: int) -> float:
        if config.inner_optimizer.warmup_steps and step < config.inner_optimizer.warmup_steps:
            return max(1e-8, float(step + 1) / float(config.inner_optimizer.warmup_steps))
        if config.inner_optimizer.scheduler == "cosine" and config.training.max_local_steps:
            progress = min(1.0, step / max(1, config.training.max_local_steps))
            return 0.5 * (1.0 + math.cos(math.pi * progress))
        return 1.0

    return optimizer, torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lr_lambda)


def maybe_autocast(device: torch.device, precision: str) -> torch.autocast:
    enabled = device.type == "cuda" and precision.lower() in {"bf16", "bfloat16"}
    return torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=enabled)


def train_one_step(
    model: torch.nn.Module,
    batch_iter: Any,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LRScheduler | None,
    *,
    device: torch.device,
    config: Config,
) -> tuple[float, int, int, float | None]:
    optimizer.zero_grad(set_to_none=True)
    total_loss = 0.0
    total_tokens = 0
    total_examples = 0
    for _ in range(config.training.gradient_accumulation_steps):
        batch: Batch = next(batch_iter).to(device)
        with maybe_autocast(device, config.training.precision):
            output = model(input_ids=batch.input_ids, labels=batch.labels)
            loss = output.loss / config.training.gradient_accumulation_steps
        if loss is None:
            raise RuntimeError("model did not return a loss")
        if not torch.isfinite(loss.detach()):
            raise FloatingPointError(f"non-finite loss: {loss.item()}")
        loss.backward()
        total_loss += float(loss.detach().cpu()) * config.training.gradient_accumulation_steps
        total_tokens += batch.num_tokens
        total_examples += batch.num_examples
    grad_norm = None
    if config.training.grad_clip is not None:
        grad_norm = float(
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.training.grad_clip).detach().cpu()
        )
    optimizer.step()
    if scheduler is not None:
        scheduler.step()
    return total_loss / config.training.gradient_accumulation_steps, total_tokens, total_examples, grad_norm


def adopt_global(
    *,
    model: torch.nn.Module,
    latest: dict[str, Any],
    param_index: dict[str, Any],
    device: torch.device,
) -> int:
    flat = load_global_weights_flat(latest["weight_path"], param_index)
    load_flat_into_model(model, flat, param_index)
    model.to(device)
    return int(latest["version"])


def write_update(
    *,
    paths: RunPaths,
    config: Config,
    learner_id: str,
    base_global_version: int,
    interval_start_step: int,
    local_step: int,
    inner_steps: int,
    tokens_this_update: int,
    tokens_since_global_load: int,
    num_examples: int,
    train_loss: float,
    grad_norm: float | None,
    param_norm: float,
    flat: torch.Tensor,
) -> tuple[str, Path, Path, dict[str, Any]]:
    update_uuid = uuid.uuid4().hex[:12]
    update_id = f"{learner_id}_{local_step:08d}_{update_uuid}"
    update_dir = paths.updates_pending / learner_id
    tensor_path = update_dir / f"update_{update_uuid}.params.safetensors"
    meta_path = update_dir / f"update_{update_uuid}.meta.json"
    created_at = time.time()
    save_update_vector(tensor_path, flat, dtype=dtype_from_name(config.io.tensor_dtype))
    digest = sha256_file(tensor_path) if config.io.compute_sha256 else None
    metadata = {
        "format_version": FORMAT_VERSION,
        "run_id": config.run.run_id,
        "update_id": update_id,
        "learner_id": learner_id,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "base_global_version": base_global_version,
        "local_step_start": interval_start_step,
        "local_step_end": local_step,
        "inner_steps": inner_steps,
        "tokens_this_update": tokens_this_update,
        "tokens_since_global_load": tokens_since_global_load,
        "num_examples_this_update": num_examples,
        "train_loss": train_loss,
        "grad_norm": grad_norm,
        "param_norm": param_norm,
        "delta_norm": None,
        "file_path": str(tensor_path),
        "file_size_bytes": file_size(tensor_path),
        "sha256": digest,
        "created_at": created_at,
        "committed_at": time.time(),
    }
    atomic_write_json(meta_path, metadata)
    return update_id, tensor_path, meta_path, metadata


def run_learner(config: Config, learner_id: str) -> None:
    paths = RunPaths(Path(config.run.shared_root or "."))
    prepare_run_dirs(paths, config.sync.num_learners)
    logger = JsonlLogger(paths.logs / f"{learner_id}.jsonl", learner_id)
    log_uncaught_exception(logger)
    learner_index = learner_index_from_id(learner_id)
    torch.manual_seed(config.training.seed + learner_index)
    device = choose_device()
    logger.event(
        "process_start",
        run_id=config.run.run_id,
        learner_id=learner_id,
        device=str(device),
        hostname=socket.gethostname(),
    )
    model, tokenizer = load_causal_lm_and_tokenizer(config.model)
    model.to(device)
    model.train()
    wait_for_json(paths.param_index_json)
    param_index = load_param_index(paths.param_index_json)
    current_index = build_param_index(model, model_name_or_path=config.model.name_or_path)
    validate_compatible_index(current_index, param_index)
    latest = wait_for_json(paths.latest_json)
    last_loaded_global_version = adopt_global(
        model=model,
        latest=latest,
        param_index=param_index,
        device=device,
    )
    optimizer, scheduler = build_inner_optimizer_and_scheduler(model, config)
    logger.event("loaded_global", version=last_loaded_global_version)
    logger.event("inner_optimizer_reset", version=last_loaded_global_version)
    write_heartbeat(
        paths=paths,
        config=config,
        learner_id=learner_id,
        status=LEARNER_STATUS_ACTIVE,
        phase="loaded_global",
        last_loaded_global_version=last_loaded_global_version,
        last_local_step=0,
        last_update_id=None,
    )

    batch_iter = build_batch_iterator(
        config,
        tokenizer,
        learner_index=learner_index,
        num_learners=config.sync.num_learners,
    )
    local_step = 0
    tokens_since_global_load = 0
    last_heartbeat = time.monotonic()
    last_update_id: str | None = None

    try:
        while not stop_requested(paths, local_step, config):
            interval_start_time = time.monotonic()
            interval_start_step = local_step
            base_global_version = last_loaded_global_version
            losses: list[float] = []
            interval_tokens = 0
            interval_examples = 0
            grad_norm: float | None = None

            for _ in range(config.training.inner_steps):
                if stop_requested(paths, local_step, config):
                    break
                loss, step_tokens, step_examples, grad_norm = train_one_step(
                    model,
                    batch_iter,
                    optimizer,
                    scheduler,
                    device=device,
                    config=config,
                )
                local_step += 1
                interval_tokens += step_tokens
                interval_examples += step_examples
                tokens_since_global_load += step_tokens
                losses.append(loss)
                if local_step % max(1, config.training.log_every_steps) == 0:
                    logger.event(
                        "inner_step_summary",
                        local_step=local_step,
                        train_loss=loss,
                        global_version=last_loaded_global_version,
                    )
                if time.monotonic() - last_heartbeat >= config.liveness.heartbeat_interval_seconds:
                    elapsed = max(1e-6, time.monotonic() - interval_start_time)
                    write_heartbeat(
                        paths=paths,
                        config=config,
                        learner_id=learner_id,
                        status=LEARNER_STATUS_ACTIVE,
                        phase="inner_steps",
                        last_loaded_global_version=last_loaded_global_version,
                        last_local_step=local_step,
                        last_update_id=last_update_id,
                        tokens_per_sec=interval_tokens / elapsed,
                    )
                    logger.event("heartbeat_written", local_step=local_step)
                    last_heartbeat = time.monotonic()
                if config.learner.poll_latest_during_inner_steps:
                    maybe_latest = read_latest_if_newer(paths, last_loaded_global_version)
                    if maybe_latest is not None:
                        last_loaded_global_version = adopt_global(
                            model=model,
                            latest=maybe_latest,
                            param_index=param_index,
                            device=device,
                        )
                        optimizer, scheduler = build_inner_optimizer_and_scheduler(model, config)
                        tokens_since_global_load = 0
                        logger.event("global_adopted", version=last_loaded_global_version)
                        logger.event("inner_optimizer_reset", version=last_loaded_global_version)

            if not losses:
                continue
            maybe_sleep_jitter(config.failure_sim)
            if should_skip_upload(config.failure_sim):
                logger.event("update_skipped", local_step=local_step)
                maybe_crash(config.failure_sim)
                continue

            write_start = time.monotonic()
            flat = flatten_trainable_params(model, param_index).float()
            param_norm = float(flat.norm().item())
            mean_loss = sum(losses) / len(losses)
            update_id, tensor_path, _meta_path, metadata = write_update(
                paths=paths,
                config=config,
                learner_id=learner_id,
                base_global_version=base_global_version,
                interval_start_step=interval_start_step,
                local_step=local_step,
                inner_steps=len(losses),
                tokens_this_update=interval_tokens,
                tokens_since_global_load=tokens_since_global_load,
                num_examples=interval_examples,
                train_loss=mean_loss,
                grad_norm=grad_norm,
                param_norm=param_norm,
                flat=flat,
            )
            write_seconds = time.monotonic() - write_start
            last_update_id = update_id
            elapsed = max(1e-6, time.monotonic() - interval_start_time)
            tokens_per_sec = interval_tokens / elapsed
            logger.event(
                "update_written",
                update_id=update_id,
                file_path=str(tensor_path),
                local_step=local_step,
                train_loss=mean_loss,
                tokens=interval_tokens,
            )
            append_csv_row(
                paths.metrics / "learner_metrics.csv",
                {
                    "timestamp": time.time(),
                    "learner_id": learner_id,
                    "local_step": local_step,
                    "global_version": last_loaded_global_version,
                    "train_loss": mean_loss,
                    "tokens": interval_tokens,
                    "tokens_per_sec": tokens_per_sec,
                    "update_write_seconds": write_seconds,
                    "param_norm": param_norm,
                    "phase": "update_written",
                },
                LEARNER_METRIC_FIELDS,
            )
            append_csv_row(
                paths.metrics / "update_manifest.csv",
                {
                    "timestamp": time.time(),
                    "update_id": update_id,
                    "learner_id": learner_id,
                    "base_global_version": base_global_version,
                    "local_step_start": interval_start_step,
                    "local_step_end": local_step,
                    "tokens_this_update": interval_tokens,
                    "file_path": metadata["file_path"],
                    "file_size_bytes": metadata["file_size_bytes"],
                    "sha256": metadata["sha256"],
                },
                UPDATE_MANIFEST_FIELDS,
            )
            write_heartbeat(
                paths=paths,
                config=config,
                learner_id=learner_id,
                status=LEARNER_STATUS_ACTIVE,
                phase="update_written",
                last_loaded_global_version=last_loaded_global_version,
                last_local_step=local_step,
                last_update_id=last_update_id,
                tokens_per_sec=tokens_per_sec,
            )
            logger.event("heartbeat_written", local_step=local_step)

            if config.learner.adopt_global_after_upload:
                maybe_latest = read_latest_if_newer(paths, last_loaded_global_version)
                logger.event(
                    "latest_polled",
                    current_version=last_loaded_global_version,
                    found_version=maybe_latest.get("version") if maybe_latest else None,
                )
                if maybe_latest is not None:
                    last_loaded_global_version = adopt_global(
                        model=model,
                        latest=maybe_latest,
                        param_index=param_index,
                        device=device,
                    )
                    optimizer, scheduler = build_inner_optimizer_and_scheduler(model, config)
                    tokens_since_global_load = 0
                    logger.event("global_adopted", version=last_loaded_global_version)
                    logger.event("inner_optimizer_reset", version=last_loaded_global_version)
            maybe_crash(config.failure_sim)
    except Exception:
        logger.exception("error", local_step=local_step, global_version=last_loaded_global_version)
        raise
    finally:
        if paths.stop_json.exists():
            stop_payload = safe_read_json(paths.stop_json) or {}
            logger.event("stop_seen", reason=stop_payload.get("reason"))
        write_heartbeat(
            paths=paths,
            config=config,
            learner_id=learner_id,
            status=LEARNER_STATUS_STOPPED,
            phase="process_exit",
            last_loaded_global_version=last_loaded_global_version,
            last_local_step=local_step,
            last_update_id=last_update_id,
        )
        logger.event("process_exit", local_step=local_step, global_version=last_loaded_global_version)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = resolve_config(
        args.config,
        run_id=args.run_id,
        shared_root=args.shared_root,
        num_learners=args.num_learners,
    )
    run_learner(config, args.learner_id)


if __name__ == "__main__":
    main()
