"""Module CLI for learner-hosted executors and floating committers."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import resource
import socket
import time

from safetensors.torch import load as load_safetensors_bytes

from fs_diloco.atomic_io import atomic_write_json, safe_read_json
from fs_diloco.config import resolve_config
from fs_diloco.log.codec import verified_get
from fs_diloco.log.layout import LogLayout
from fs_diloco.log.production_codec import decode_production_outer_state, decode_production_params
from fs_diloco.logging_utils import JsonlLogger
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.work_order_v2 import RedundantFragmentWorkOrderV2
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.syncer_core.capabilities import PrepareObjectFacade

from .executor import ExecutorBudget, execute_work_order
from .bootstrap import revision_zero_membership
from .committer import run_committer
from .input_bundle import load_input_bundle
from .hedge_policy import RedundancyPolicyV1, execution_eligible
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
    available_cpus = tuple(sorted(os.sched_getaffinity(0)))
    executor_cpus = available_cpus[-min(len(available_cpus), budget.threads) :]
    os.sched_setaffinity(0, executor_cpus)
    numa_mems = None
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Mems_allowed_list:"):
                numa_mems = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    telemetry = JsonlLogger(
        shared / "logs" / f"distributed_executor_{args.member_id}.jsonl",
        f"distributed_executor:{args.member_id}",
    )
    telemetry.event(
        "executor_started",
        member_id=args.member_id,
        executor_id=args.executor_id,
        executor_session_id=args.executor_session_id,
        threads=budget.threads,
        max_inflight=budget.max_inflight,
        max_rss_bytes=budget.max_rss_bytes,
        cpu_affinity=list(executor_cpus),
        numa_mems_allowed_list=numa_mems,
    )
    active_path = shared / "distributed" / "active_work_order.json"
    heartbeat_path = shared / "distributed" / "executors" / f"{args.member_id}.json"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    completed: set[str] = set()
    while not (shared / "control" / "stop.json").exists():
        dispatch = safe_read_json(active_path)
        raw_owner_ids = dispatch.get("owner_member_ids") if isinstance(dispatch, dict) else None
        if raw_owner_ids is None and isinstance(dispatch, dict):
            legacy_owner = dispatch.get("owner_member_id")
            raw_owner_ids = [legacy_owner] if isinstance(legacy_owner, str) else None
        if (
            not isinstance(dispatch, dict)
            or not isinstance(raw_owner_ids, list)
            or not raw_owner_ids
            or any(not isinstance(value, str) or not value for value in raw_owner_ids)
            or args.member_id not in raw_owner_ids
        ):
            atomic_write_json(
                heartbeat_path,
                {
                    "member_id": args.member_id,
                    "status": "idle",
                    "hostname": socket.gethostname(),
                    "timestamp": time.time(),
                },
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
        owner_member_ids = tuple(raw_owner_ids)
        if isinstance(order, RedundantFragmentWorkOrderV2):
            if owner_member_ids != order.owner_member_ids:
                raise ValueError("derived owner roles differ from authoritative work order")
            owner_role = "primary" if args.member_id == order.primary_member_id else "backup"
            failed_member_ids = dispatch.get("failed_member_ids", [])
            if (
                not isinstance(failed_member_ids, list)
                or any(not isinstance(value, str) for value in failed_member_ids)
                or not set(failed_member_ids).issubset(order.owner_member_ids)
            ):
                raise ValueError("derived dispatch has invalid failed-member evidence")
            if args.member_id in failed_member_ids:
                atomic_write_json(
                    heartbeat_path,
                    {
                        "member_id": args.member_id,
                        "status": "failure_observed",
                        "work_order_id": order.work_order_id,
                        "owner_role": owner_role,
                        "redundancy_mode": order.redundancy_policy.mode,
                        "timestamp": time.time(),
                    },
                )
                time.sleep(args.poll_seconds)
                continue
            published_at = dispatch.get("published_at")
            if not isinstance(published_at, (int, float)) or isinstance(published_at, bool):
                raise ValueError("derived dispatch has invalid publication time")
            backup_activated = dispatch.get("backup_activated", False)
            elapsed_ms = max(0, int((time.time() - float(published_at)) * 1000))
            if not execution_eligible(
                order.redundancy_policy,
                owner_role=owner_role,
                elapsed_ms=elapsed_ms,
                backup_activated=backup_activated,
            ):
                atomic_write_json(
                    heartbeat_path,
                    {
                        "member_id": args.member_id,
                        "status": "standby",
                        "work_order_id": order.work_order_id,
                        "owner_role": owner_role,
                        "redundancy_mode": order.redundancy_policy.mode,
                        "timestamp": time.time(),
                    },
                )
                time.sleep(args.poll_seconds)
                continue
        else:
            if len(owner_member_ids) != 1:
                raise ValueError("factor-one dispatch must name exactly one owner")
            owner_role = "primary"
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
            {
                "member_id": args.member_id,
                "status": "preparing",
                "work_order_id": order.work_order_id,
                "owner_role": owner_role,
                "timestamp": time.time(),
            },
        )
        prepare_started_at = time.time()
        prepare_started = time.monotonic()
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
        prepare_seconds = time.monotonic() - prepare_started
        input_bytes = bundle.params_ref.size + bundle.outer_state_ref.size + sum(
            item.payload_ref.size for item in bundle.proposals
        )
        output_bytes = result.params_ref.size + result.outer_state_ref.size
        resource_snapshot = {
            "member_id": args.member_id,
            "executor_id": args.executor_id,
            "executor_session_id": args.executor_session_id,
            "work_order_id": order.work_order_id,
            "prepared_result_id": result.prepared_result_id,
            "attempt_envelope_id": envelope.attempt_envelope_id,
            "owner_role": owner_role,
            "redundancy_mode": (
                order.redundancy_policy.mode
                if isinstance(order, RedundantFragmentWorkOrderV2)
                else "factor_one"
            ),
            "prepare_started_at": prepare_started_at,
            "prepare_finished_at": time.time(),
            "prepare_seconds": prepare_seconds,
            "rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "threads": budget.threads,
            "cpu_affinity": list(executor_cpus),
            "numa_mems_allowed_list": numa_mems,
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
            "logical_input_reads": 2 + len(bundle.proposals),
            "logical_prepare_writes": 5,
        }
        telemetry.event("fragment_prepared", **resource_snapshot)
        atomic_write_json(
            heartbeat_path,
            {
                "member_id": args.member_id,
                "status": "prepared",
                **resource_snapshot,
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
    committer.add_argument("--replication-factor", type=int, choices=(1, 2), default=1)
    committer.add_argument(
        "--execution-mode", choices=("warm_standby", "active_active", "hedged")
    )
    committer.add_argument("--hedge-delay-ms", type=int)
    committer.add_argument("--lifecycle-cadence", type=int, default=0)
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
        redundancy_policy = None
        if args.replication_factor == 2:
            if args.execution_mode is None:
                raise ValueError("factor-two committer requires --execution-mode")
            policy_payload: dict[str, object] = {"mode": args.execution_mode}
            if args.execution_mode == "hedged":
                policy_payload["hedge_delay_ms"] = args.hedge_delay_ms
            elif args.hedge_delay_ms is not None:
                raise ValueError("--hedge-delay-ms is valid only for hedged mode")
            redundancy_policy = RedundancyPolicyV1.from_dict(policy_payload)
        elif args.execution_mode is not None or args.hedge_delay_ms is not None:
            raise ValueError("factor-one committer cannot configure redundancy mode")
        run_committer(
            config,
            membership=membership,
            budget=budget,
            member_id=args.member_id,
            owner_session_id=args.owner_session_id,
            standby=args.standby,
            replication_factor=args.replication_factor,
            redundancy_policy=redundancy_policy,
            lifecycle_cadence=args.lifecycle_cadence,
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
