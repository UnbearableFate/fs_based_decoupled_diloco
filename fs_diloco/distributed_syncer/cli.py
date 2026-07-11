"""Module CLI for learner-hosted executors and floating committers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import time

from safetensors.torch import load as load_safetensors_bytes

from fs_diloco.atomic_io import atomic_write_json, safe_read_json
from fs_diloco.config import resolve_config
from fs_diloco.log.codec import verified_get
from fs_diloco.log.layout import LogLayout
from fs_diloco.log.production_codec import decode_production_outer_state, decode_production_params
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.syncer_core.capabilities import PrepareObjectFacade

from .executor import ExecutorBudget, execute_work_order
from .bootstrap import revision_zero_membership
from .committer import run_committer
from .input_bundle import load_input_bundle
from .layout import DistributedLayout
from .work_order_store import load_work_order


def _executor(args: argparse.Namespace) -> int:
    config = resolve_config(
        args.config,
        run_id=args.run_id,
        shared_root=args.shared_root,
        num_learners=args.num_learners,
    )
    shared = Path(config.run.shared_root or ".")
    backend = PosixStorageBackend(shared / "authority")
    layout = DistributedLayout(LogLayout(config.run.run_id or "", config.init.run_generation))
    facade = PrepareObjectFacade(
        backend,
        read_prefixes=(layout.log.immutable_prefix,),
        write_prefixes=(layout.prepared_prefix,),
    )
    budget = ExecutorBudget(
        threads=args.threads,
        max_inflight=1,
        max_rss_bytes=args.max_rss_bytes,
    )
    active_path = shared / "distributed" / "active_work_order.json"
    heartbeat_path = shared / "distributed" / "executors" / f"{args.member_id}.json"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    completed: set[str] = set()
    while not (shared / "control" / "stop.json").exists():
        dispatch = safe_read_json(active_path)
        if not isinstance(dispatch, dict) or dispatch.get("owner_member_id") != args.member_id:
            atomic_write_json(
                heartbeat_path,
                {"member_id": args.member_id, "status": "idle", "hostname": socket.gethostname(), "timestamp": time.time()},
            )
            time.sleep(args.poll_seconds)
            continue
        work_order_id = str(dispatch.get("work_order_id") or "")
        if not work_order_id or work_order_id in completed:
            time.sleep(args.poll_seconds)
            continue
        order = load_work_order(facade, layout, work_order_id)
        if (
            order.ownership_digest != dispatch.get("ownership_digest")
            or order.membership_revision != int(dispatch.get("membership_revision", -1))
        ):
            raise ValueError("derived dispatch differs from authoritative work order")
        bundle = load_input_bundle(facade, layout, work_order_id)
        if bundle.parent_commit_id != order.parent_commit_id:
            raise ValueError("input bundle parent differs from work order")
        params = decode_production_params(verified_get(facade, bundle.params_ref, commit_seq=0))
        outer = decode_production_outer_state(
            verified_get(facade, bundle.outer_state_ref, commit_seq=0)
        )
        tensors = {}
        for item in bundle.proposals:
            data = verified_get(facade, item.payload_ref, commit_seq=0)
            decoded = load_safetensors_bytes(data)
            tensors[item.proposal_id] = decoded[item.tensor_key].float().reshape(-1)
        attempt_id = "attempt-" + canonical_digest(
            {
                "work_order_id": order.work_order_id,
                "executor_id": args.executor_id,
                "executor_session_id": args.executor_session_id,
            }
        )
        resource_digest = canonical_digest(
            {"budget": budget.to_dict(), "hostname": socket.gethostname()}
        )
        atomic_write_json(
            heartbeat_path,
            {"member_id": args.member_id, "status": "preparing", "work_order_id": order.work_order_id, "timestamp": time.time()},
        )
        result, envelope = execute_work_order(
            facade=facade,
            layout=layout,
            order=order,
            current_params=params,
            current_outer_state=outer,
            proposal_tensors=tensors,
            optimizer_config=config.outer_optimizer,
            executor_id=args.executor_id,
            executor_session_id=args.executor_session_id,
            attempt_id=attempt_id,
            resource_evidence_digest=resource_digest,
            budget=budget,
        )
        completed.add(order.work_order_id)
        atomic_write_json(
            heartbeat_path,
            {
                "member_id": args.member_id,
                "status": "prepared",
                "work_order_id": order.work_order_id,
                "prepared_result_id": result.prepared_result_id,
                "attempt_envelope_id": envelope.attempt_envelope_id,
                "timestamp": time.time(),
            },
        )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    executor = sub.add_parser("executor")
    executor.add_argument("--config", required=True)
    executor.add_argument("--run-id", required=True)
    executor.add_argument("--shared-root", required=True)
    executor.add_argument("--num-learners", required=True, type=int)
    executor.add_argument("--member-id", required=True)
    executor.add_argument("--executor-id", required=True)
    executor.add_argument("--executor-session-id", required=True)
    executor.add_argument("--threads", type=int, default=8)
    executor.add_argument("--max-rss-bytes", type=int, default=16 * 1024**3)
    executor.add_argument("--poll-seconds", type=float, default=0.1)
    committer = sub.add_parser("committer")
    committer.add_argument("--config", required=True)
    committer.add_argument("--run-id", required=True)
    committer.add_argument("--shared-root", required=True)
    committer.add_argument("--num-learners", required=True, type=int)
    committer.add_argument("--node-ids", required=True)
    committer.add_argument("--member-id", required=True)
    committer.add_argument("--owner-session-id", required=True)
    committer.add_argument("--threads", type=int, default=8)
    committer.add_argument("--max-rss-bytes", type=int, default=16 * 1024**3)
    committer.add_argument("--standby", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "executor":
        return _executor(args)
    if args.command == "committer":
        config = resolve_config(
            args.config,
            run_id=args.run_id,
            shared_root=args.shared_root,
            num_learners=args.num_learners,
        )
        budget = ExecutorBudget(
            threads=args.threads,
            max_inflight=1,
            max_rss_bytes=args.max_rss_bytes,
        )
        node_ids = tuple(item for item in args.node_ids.split(",") if item)
        learner_ids = tuple(f"learner_{index:03d}" for index in range(args.num_learners))
        membership = revision_zero_membership(
            run_id=args.run_id,
            learner_ids=learner_ids,
            node_ids=node_ids,
            budget=budget,
        )
        run_committer(
            config,
            membership=membership,
            budget=budget,
            member_id=args.member_id,
            owner_session_id=args.owner_session_id,
            standby=args.standby,
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
