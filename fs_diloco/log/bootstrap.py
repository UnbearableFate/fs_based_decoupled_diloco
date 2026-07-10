"""Explicit checkpoint-only warm start into a fresh run generation."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import torch

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.config import resolve_config, write_resolved_config
from fs_diloco.fragment_codec import extract_fragment, load_fragment_weight
from fs_diloco.fragment_index import fragment_layout_digest, load_fragment_index
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.param_index import load_param_index, param_index_digest
from fs_diloco.paths import RunPaths, prepare_run_dirs
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.syncer import _run_spec, publish_materialized_view
from fs_diloco.tensor_codec import load_global_weights_flat, load_outer_state

from .production import ProductionTransactionalLog
from .production_codec import encode_production_outer_state, encode_production_params


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(items: list[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for item in items:
        raw_id, separator, raw_path = item.partition("=")
        if not separator:
            raise ValueError("checkpoint mappings must use FRAGMENT_ID=PATH")
        fragment_id = int(raw_id)
        if fragment_id in result:
            raise ValueError(f"duplicate fragment mapping: {fragment_id}")
        result[fragment_id] = Path(raw_path).resolve()
    return result


def bootstrap_new_generation(
    *,
    config_path: Path,
    run_id: str,
    generation: int,
    shared_root: Path,
    params_paths: dict[int, Path],
    outer_paths: dict[int, Path],
) -> dict[str, object]:
    if generation < 1:
        raise ValueError("warm start requires a fresh generation greater than zero")
    config = resolve_config(
        config_path,
        run_id=run_id,
        shared_root=str(shared_root),
        project_root=Path.cwd(),
    )
    config.init.resume = False
    config.init.run_generation = generation
    paths = RunPaths(Path(config.run.shared_root or shared_root))
    prepare_run_dirs(paths, config.sync.num_learners)
    param_index = load_param_index(paths.param_index_json)
    fragment_index = load_fragment_index(paths.fragment_index_json)
    expected = {int(item["fragment_id"]) for item in fragment_index["fragments"]}
    if set(params_paths) != expected or not set(outer_paths).issubset(expected):
        raise ValueError("checkpoint mappings do not match the frozen fragment layout")

    source_digests = tuple(
        sorted({_sha256(path) for path in [*params_paths.values(), *outer_paths.values()]})
    )
    spec = replace(
        _run_spec(
            config,
            parameter_digest=param_index_digest(param_index),
            layout_digest=fragment_layout_digest(fragment_index),
        ),
        generation_kind="warm_start",
        source_checkpoint_digests=source_digests,
    )
    fragments: dict[int, torch.Tensor] = {}
    states: dict[int, dict[str, torch.Tensor]] = {}
    initial: dict[int, tuple[bytes, bytes]] = {}
    for fragment_id in sorted(expected):
        if len(expected) == 1:
            params = load_global_weights_flat(params_paths[fragment_id], param_index)
        else:
            params = load_fragment_weight(params_paths[fragment_id])
        if fragment_id in outer_paths:
            outer_theta, state = load_outer_state(outer_paths[fragment_id])
            if int(outer_theta.numel()) != int(params.numel()):
                raise ValueError(f"fragment {fragment_id} params and outer checkpoint differ")
        else:
            state = init_outer_state(params, config.outer_optimizer)
        fragments[fragment_id] = params.float()
        states[fragment_id] = state
        initial[fragment_id] = (
            encode_production_params(params),
            encode_production_outer_state(state),
        )

    log = ProductionTransactionalLog.initialize(
        PosixStorageBackend(paths.authority),
        spec,
        initial,
    )
    view = build_runtime_view(log)
    write_resolved_config(config, paths.resolved_config_yaml)
    publish_materialized_view(
        config=config,
        paths=paths,
        view=view,
        param_index=param_index,
        fragment_index=fragment_index,
        fragment_thetas=fragments,
        outer_states=states,
    )
    receipt = {
        "schema_version": 1,
        "kind": "checkpoint-only-new-generation-warm-start",
        "run_id": run_id,
        "run_generation": generation,
        "commit_id": view.commit_id,
        "frontier_sha256": view.frontier_sha256,
        "source_checkpoint_digests": list(source_digests),
        "imported_proposal_history": False,
        "exact_continuation": False,
    }
    atomic_write_json(paths.control / "bootstrap_receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--params", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--outer", action="append", default=[], metavar="ID=PATH")
    args = parser.parse_args(argv)
    result = bootstrap_new_generation(
        config_path=args.config,
        run_id=args.run_id,
        generation=args.generation,
        shared_root=args.shared_root,
        params_paths=_mapping(args.params),
        outer_paths=_mapping(args.outer),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
