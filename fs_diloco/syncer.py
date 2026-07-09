"""Filesystem-backed Decoupled DiLoCo syncer."""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

import torch

from .atomic_io import atomic_write_json, read_json, safe_read_json
from .config import Config, config_to_dict, resolve_config, write_resolved_config
from .constants import FORMAT_VERSION, GLOBAL_STATUS_COMMITTED, learner_id_from_index
from .hf_model import choose_device, load_causal_lm_and_tokenizer
from .liveness import ingest_heartbeats, no_progress_timed_out, update_liveness_statuses
from .logging_utils import JsonlLogger, log_uncaught_exception
from .merge import normalized_update_weights, select_one_per_learner, weighted_average_tensors
from .metrics import SYNCER_METRIC_FIELDS, append_csv_row
from .outer_optim import init_outer_state, outer_optimizer_step
from .param_index import (
    build_param_index,
    flatten_trainable_params,
    load_param_index,
    validate_compatible_index,
)
from .paths import RunPaths, prepare_run_dirs
from .sqlite_store import SQLiteStore
from .tensor_codec import (
    load_global_weights_flat,
    load_outer_state,
    load_update_vector,
    save_global_weights,
    save_outer_state,
)
from .wandb_logging import (
    selected_update_summary,
    syncer_wandb_project_name,
    syncer_wandb_run_name,
    syncer_wandb_tags,
    wandb_config,
    wandb_is_disabled,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--shared-root")
    parser.add_argument("--sqlite-local-dir")
    parser.add_argument("--num-learners", type=int)
    return parser.parse_args(argv)


def sqlite_path(config: Config) -> Path:
    run_id = config.run.run_id or "unknown_run"
    local_dir = config.io.sqlite_local_dir
    if local_dir is None:
        local_dir = str(Path(os.environ.get("TMPDIR", "/tmp")) / "fs_diloco" / run_id)
    return Path(local_dir) / "syncer_metadata.sqlite3"


def latest_payload(
    *,
    config: Config,
    paths: RunPaths,
    version: int,
    weight_path: Path,
    optim_path: Path,
    total_seen_tokens: int,
) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "run_id": config.run.run_id,
        "version": version,
        "weight_path": str(weight_path),
        "optim_path": str(optim_path),
        "param_index_path": str(paths.param_index_json),
        "created_at": time.time(),
        "total_seen_tokens": total_seen_tokens,
    }


def publish_global(
    *,
    config: Config,
    paths: RunPaths,
    store: SQLiteStore,
    version: int,
    theta: torch.Tensor,
    outer_state: dict[str, torch.Tensor],
    param_index: dict[str, Any],
    num_updates: int,
    total_update_tokens: int,
    total_seen_tokens: int,
) -> None:
    weight_path = paths.global_weight_path(version)
    optim_path = paths.outer_optim_path(version)
    save_global_weights(weight_path, theta, param_index)
    save_outer_state(optim_path, theta, outer_state)
    store.upsert_global_version(
        version,
        str(weight_path),
        str(optim_path),
        num_updates=num_updates,
        total_update_tokens=total_update_tokens,
        total_seen_tokens=total_seen_tokens,
        outer_optimizer=config.outer_optimizer.name,
        status=GLOBAL_STATUS_COMMITTED,
    )
    atomic_write_json(
        paths.latest_json,
        latest_payload(
            config=config,
            paths=paths,
            version=version,
            weight_path=weight_path,
            optim_path=optim_path,
            total_seen_tokens=total_seen_tokens,
        ),
    )


def initialize_run(
    config: Config,
    paths: RunPaths,
    store: SQLiteStore,
    logger: JsonlLogger,
    *,
    device: torch.device | str = "cpu",
) -> tuple[int, torch.Tensor, dict[str, torch.Tensor], dict[str, Any], int]:
    if paths.latest_json.exists() and not config.init.allow_overwrite_existing_run:
        raise FileExistsError(f"{paths.latest_json} exists; set init.resume or allow overwrite")
    model, _tokenizer = load_causal_lm_and_tokenizer(config.model)
    model.to(device)
    param_index = build_param_index(model, model_name_or_path=config.model.name_or_path)
    theta = flatten_trainable_params(model, param_index, device=device).float()
    outer_state = init_outer_state(theta, config.outer_optimizer)
    atomic_write_json(paths.param_index_json, param_index)
    write_resolved_config(config, paths.resolved_config_yaml)
    publish_global(
        config=config,
        paths=paths,
        store=store,
        version=0,
        theta=theta,
        outer_state=outer_state,
        param_index=param_index,
        num_updates=0,
        total_update_tokens=0,
        total_seen_tokens=0,
    )
    store.set_run_state("config", config_to_dict(config))
    store.insert_event("syncer", "run_initialized", global_version=0)
    logger.event("run_initialized", version=0, total_numel=int(theta.numel()))
    return 0, theta, outer_state, param_index, 0


def _resume_latest_payload(config: Config, paths: RunPaths) -> dict[str, Any]:
    if config.init.resume_version == "latest":
        return read_json(paths.latest_json)
    version = int(config.init.resume_version)
    return {
        "format_version": FORMAT_VERSION,
        "run_id": config.run.run_id,
        "version": version,
        "weight_path": str(paths.global_weight_path(version)),
        "optim_path": str(paths.outer_optim_path(version)),
        "param_index_path": str(paths.param_index_json),
        "total_seen_tokens": 0,
    }


def _newest_db_dump(paths: RunPaths, version: int) -> Path | None:
    dumps = sorted(paths.db_dumps.glob(f"metadata_*_v{version:06d}.db"))
    return dumps[-1] if dumps else None


def resume_run(
    config: Config,
    paths: RunPaths,
    store: SQLiteStore,
    logger: JsonlLogger,
    *,
    device: torch.device | str = "cpu",
) -> tuple[int, torch.Tensor, dict[str, torch.Tensor], dict[str, Any], int]:
    latest = _resume_latest_payload(config, paths)
    param_index = load_param_index(latest["param_index_path"])
    model, _tokenizer = load_causal_lm_and_tokenizer(config.model)
    current_index = build_param_index(model, model_name_or_path=config.model.name_or_path)
    validate_compatible_index(current_index, param_index)
    theta = load_global_weights_flat(latest["weight_path"], param_index, device=device)
    optim_theta, outer_state = load_outer_state(latest["optim_path"], device=device)
    if optim_theta.numel() == theta.numel():
        theta = optim_theta.float()

    requested_dump = Path(config.init.resume_db_dump) if config.init.resume_db_dump else None
    dump = requested_dump or _newest_db_dump(paths, int(latest["version"]))
    if dump and dump.exists():
        row = store.conn.execute("SELECT COUNT(*) AS n FROM global_versions").fetchone()
        if row["n"] == 0:
            store.restore_from_dump(dump)
    total_seen_tokens = int(latest.get("total_seen_tokens") or 0)
    store.upsert_global_version(
        int(latest["version"]),
        latest["weight_path"],
        latest["optim_path"],
        num_updates=0,
        total_update_tokens=0,
        total_seen_tokens=total_seen_tokens,
        outer_optimizer=config.outer_optimizer.name,
        status=GLOBAL_STATUS_COMMITTED,
        notes="resumed",
    )
    logger.event("run_resumed", version=int(latest["version"]), db_dump=str(dump) if dump else None)
    return int(latest["version"]), theta.float().to(device), outer_state, param_index, total_seen_tokens


def validate_update_metadata(payload: dict[str, Any], *, config: Config, paths: RunPaths) -> bool:
    if payload.get("format_version") != FORMAT_VERSION:
        return False
    if payload.get("run_id") != config.run.run_id:
        return False
    valid_ids = {learner_id_from_index(i) for i in range(config.sync.num_learners)}
    if payload.get("learner_id") not in valid_ids:
        return False
    file_path = Path(payload.get("file_path", ""))
    if not file_path.exists():
        return False
    try:
        file_path.relative_to(paths.shared_root)
    except ValueError:
        pass
    return True


def ingest_update_metadata(
    store: SQLiteStore,
    paths: RunPaths,
    config: Config,
    logger: JsonlLogger,
) -> int:
    inserted = 0
    for path in sorted(paths.updates_pending.glob("learner_*/update_*.meta.json")):
        payload = safe_read_json(path)
        if payload is None or not validate_update_metadata(payload, config=config, paths=paths):
            continue
        if store.insert_update_metadata(payload):
            inserted += 1
            store.insert_event(
                "syncer",
                "metadata_ingested",
                learner_id=payload["learner_id"],
                update_id=payload["update_id"],
                payload={"path": str(path)},
            )
    if inserted:
        logger.event("metadata_ingested", count=inserted)
    return inserted


def sync_liveness_and_metadata(
    store: SQLiteStore,
    paths: RunPaths,
    config: Config,
    logger: JsonlLogger,
) -> None:
    heartbeat_count = ingest_heartbeats(
        store,
        paths.heartbeats,
        run_id=config.run.run_id or "",
        num_learners=config.sync.num_learners,
    )
    counts = update_liveness_statuses(
        store,
        stale_after_seconds=config.liveness.stale_after_seconds,
        dead_after_seconds=config.liveness.dead_after_seconds,
    )
    if heartbeat_count:
        logger.event("heartbeats_ingested", count=heartbeat_count)
        logger.event("learner_liveness_updated", **counts)
    ingest_update_metadata(store, paths, config, logger)


def collect_with_grace_window(
    store: SQLiteStore,
    paths: RunPaths,
    config: Config,
    logger: JsonlLogger,
    *,
    current_version: int,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + min(
        config.sync.grace_window.fixed_seconds,
        config.sync.grace_window.max_seconds,
    )
    selected: list[dict[str, Any]] = []
    while True:
        eligible = store.eligible_updates(current_version, config.sync.max_staleness_versions)
        eligible = [row for row in eligible if Path(row["file_path"]).exists()]
        selected = select_one_per_learner(
            eligible,
            policy=config.sync.selection_policy,
            quorum_max=config.sync.quorum_max,
        )
        if len(selected) >= config.sync.quorum_max:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(min(config.sync.scan_interval_seconds, max(0.0, deadline - time.monotonic())))
        sync_liveness_and_metadata(store, paths, config, logger)
    return selected


def dump_db(store: SQLiteStore, paths: RunPaths, version: int, logger: JsonlLogger) -> None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = paths.db_dump_path(timestamp, version)
    store.backup_to(path, global_version=version)
    logger.event("db_dumped", version=version, path=str(path))


def init_wandb_run(
    *,
    config: Config,
    paths: RunPaths,
    logger: JsonlLogger,
    device: torch.device,
    hostname: str,
) -> Any | None:
    if wandb_is_disabled(config):
        logger.event("wandb_disabled")
        return None
    try:
        import wandb
    except Exception as exc:
        logger.event("wandb_unavailable", error=repr(exc))
        return None

    project_name = syncer_wandb_project_name(config)
    run_name = syncer_wandb_run_name(config)
    mode = os.environ.get("WANDB_MODE") or config.wandb.mode
    run_id = f"syncer-{config.run.run_id}" if config.run.run_id else None
    kwargs: dict[str, Any] = {
        "project": project_name,
        "name": run_name,
        "id": run_id,
        "resume": "allow",
        "config": wandb_config(
            config,
            device=str(device),
            hostname=hostname,
            shared_root=str(paths.shared_root),
        ),
        "tags": syncer_wandb_tags(config),
        "dir": str(paths.logs),
    }
    if mode:
        kwargs["mode"] = mode
    if config.wandb.entity:
        kwargs["entity"] = config.wandb.entity
    kwargs["group"] = config.wandb.group or config.run.name

    try:
        run = wandb.init(**kwargs)
        wandb.define_metric("syncer/version")
        wandb.define_metric("*", step_metric="syncer/version")
    except Exception as exc:
        logger.event("wandb_init_failed", project=project_name, run_name=run_name, error=repr(exc))
        return None
    logger.event("wandb_initialized", project=project_name, run_name=run_name, mode=mode)
    return run


def publish_stop(
    paths: RunPaths,
    *,
    config: Config,
    reason: str,
    version: int,
    total_seen_tokens: int,
) -> None:
    atomic_write_json(
        paths.stop_json,
        {
            "format_version": FORMAT_VERSION,
            "run_id": config.run.run_id,
            "reason": reason,
            "version": version,
            "total_seen_tokens": total_seen_tokens,
            "timestamp": time.time(),
        },
    )


def run_syncer(config: Config) -> None:
    paths = RunPaths(Path(config.run.shared_root or "."))
    prepare_run_dirs(paths, config.sync.num_learners)
    store = SQLiteStore(sqlite_path(config))
    logger = JsonlLogger(paths.logs / "syncer.jsonl", "syncer")
    log_uncaught_exception(logger)
    device = choose_device()
    hostname = socket.gethostname()
    logger.event(
        "process_start",
        run_id=config.run.run_id,
        shared_root=str(paths.shared_root),
        sqlite_path=str(store.path),
        hostname=hostname,
        device=str(device),
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
    )
    wandb_run = init_wandb_run(
        config=config,
        paths=paths,
        logger=logger,
        device=device,
        hostname=hostname,
    )
    if config.init.resume:
        version, theta, outer_state, param_index, total_seen_tokens = resume_run(
            config,
            paths,
            store,
            logger,
            device=device,
        )
    else:
        version, theta, outer_state, param_index, total_seen_tokens = initialize_run(
            config,
            paths,
            store,
            logger,
            device=device,
        )

    last_progress_time = time.time()
    last_global_time = last_progress_time
    stop_reason = "completed"
    try:
        while True:
            if config.sync.stop_after_outer_steps is not None and version >= config.sync.stop_after_outer_steps:
                stop_reason = "stop_after_outer_steps"
                break
            if (
                config.sync.stop_after_global_tokens is not None
                and total_seen_tokens >= config.sync.stop_after_global_tokens
            ):
                stop_reason = "stop_after_global_tokens"
                break

            sync_liveness_and_metadata(store, paths, config, logger)
            eligible = store.eligible_updates(version, config.sync.max_staleness_versions)
            eligible = [row for row in eligible if Path(row["file_path"]).exists()]
            one_per_learner = select_one_per_learner(
                eligible,
                policy=config.sync.selection_policy,
                quorum_max=config.sync.quorum_max,
            )
            if len(one_per_learner) < config.sync.quorum_min:
                logger.event(
                    "quorum_wait",
                    eligible=len(one_per_learner),
                    quorum_min=config.sync.quorum_min,
                    version=version,
                )
                if no_progress_timed_out(
                    last_progress_time,
                    config.liveness.no_progress_timeout_seconds,
                ):
                    stop_reason = "no_progress_timeout"
                    logger.event("no_progress_timeout", version=version)
                    break
                time.sleep(config.sync.scan_interval_seconds)
                continue

            selected = collect_with_grace_window(
                store,
                paths,
                config,
                logger,
                current_version=version,
            )
            if len(selected) < config.sync.quorum_min:
                continue

            run_selection_id = f"{config.run.run_id}_v{version + 1:06d}"
            store.mark_updates_selected([row["update_id"] for row in selected], run_selection_id)
            logger.event(
                "updates_selected",
                version=version,
                update_ids=[row["update_id"] for row in selected],
                learners=[row["learner_id"] for row in selected],
            )

            read_start = time.monotonic()
            vectors = [load_update_vector(row["file_path"], device=device) for row in selected]
            read_seconds = time.monotonic() - read_start

            weights_by_update = normalized_update_weights(
                selected,
                current_version=version,
                staleness_lambda=config.sync.staleness_lambda,
            )
            weights = [weights_by_update[row["update_id"]] for row in selected]
            aggregation_start = time.monotonic()
            p_bar = weighted_average_tensors(vectors, weights)
            grad = theta - p_bar
            aggregation_seconds = time.monotonic() - aggregation_start

            outer_start = time.monotonic()
            theta, outer_state = outer_optimizer_step(theta, grad, outer_state, config.outer_optimizer)
            outer_seconds = time.monotonic() - outer_start

            new_version = version + 1
            total_update_tokens = sum(int(row["tokens_this_update"]) for row in selected)
            total_seen_tokens += total_update_tokens
            publish_start = time.monotonic()
            publish_global(
                config=config,
                paths=paths,
                store=store,
                version=new_version,
                theta=theta,
                outer_state=outer_state,
                param_index=param_index,
                num_updates=len(selected),
                total_update_tokens=total_update_tokens,
                total_seen_tokens=total_seen_tokens,
            )
            publish_seconds = time.monotonic() - publish_start

            store.mark_updates_applied(
                selected,
                applied_version=new_version,
                effective_weights=weights_by_update,
            )
            dropped = store.drop_superseded_updates(selected)
            dropped += store.drop_obsolete_updates(new_version, config.sync.max_staleness_versions)
            if config.sync.db_dump_every_versions and new_version % config.sync.db_dump_every_versions == 0:
                dump_db(store, paths, new_version, logger)
            append_csv_row(
                paths.metrics / "syncer_metrics.csv",
                {
                    "timestamp": time.time(),
                    "version": new_version,
                    "selected_count": len(selected),
                    "total_update_tokens": total_update_tokens,
                    "read_seconds": read_seconds,
                    "aggregation_seconds": aggregation_seconds,
                    "outer_step_seconds": outer_seconds,
                    "publish_seconds": publish_seconds,
                    "stale_updates_dropped": dropped,
                    "global_interval_seconds": time.time() - last_global_time,
                },
                SYNCER_METRIC_FIELDS,
            )
            if wandb_run is not None:
                wandb_run.log(
                    {
                        "syncer/version": new_version,
                        "syncer/selected_count": len(selected),
                        "syncer/total_update_tokens": total_update_tokens,
                        "syncer/total_seen_tokens": total_seen_tokens,
                        "syncer/read_seconds": read_seconds,
                        "syncer/aggregation_seconds": aggregation_seconds,
                        "syncer/outer_step_seconds": outer_seconds,
                        "syncer/publish_seconds": publish_seconds,
                        "syncer/stale_updates_dropped": dropped,
                        "syncer/global_interval_seconds": time.time() - last_global_time,
                        **selected_update_summary(selected, current_version=version),
                    },
                    step=new_version,
                )
            logger.event(
                "outer_step_applied",
                version=new_version,
                selected_count=len(selected),
                total_update_tokens=total_update_tokens,
            )
            logger.event("global_published", version=new_version)
            logger.event("updates_marked_applied", version=new_version)
            if dropped:
                logger.event("updates_dropped", version=new_version, count=dropped)
            version = new_version
            last_progress_time = time.time()
            last_global_time = last_progress_time
    except Exception:
        stop_reason = "error"
        logger.exception("error", version=version)
        raise
    finally:
        try:
            publish_stop(
                paths,
                config=config,
                reason=stop_reason,
                version=version,
                total_seen_tokens=total_seen_tokens,
            )
            logger.event("stop_published", reason=stop_reason, version=version)
            dump_db(store, paths, version, logger)
            if wandb_run is not None:
                wandb_run.summary["stop_reason"] = stop_reason
                wandb_run.summary["final_version"] = version
                wandb_run.summary["total_seen_tokens"] = total_seen_tokens
            logger.event("process_exit", reason=stop_reason, version=version)
        finally:
            try:
                if wandb_run is not None:
                    wandb_run.finish(exit_code=1 if stop_reason == "error" else 0)
            finally:
                store.close()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = resolve_config(
        args.config,
        run_id=args.run_id,
        shared_root=args.shared_root,
        sqlite_local_dir=args.sqlite_local_dir,
        num_learners=args.num_learners,
    )
    run_syncer(config)


if __name__ == "__main__":
    main()
