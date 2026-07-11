"""Logical immutable keys for distributed work orders and prepared results."""

from __future__ import annotations

from dataclasses import dataclass

from fs_diloco.log.layout import LogLayout


@dataclass(frozen=True)
class DistributedLayout:
    log: LogLayout

    @property
    def work_order_prefix(self) -> str:
        return f"{self.log.root}/immutable/distributed/work-orders/"

    @property
    def prepared_prefix(self) -> str:
        return f"{self.log.root}/immutable/distributed/prepared/"

    def work_order_key(self, work_order_id: str) -> str:
        return f"{self.work_order_prefix}{work_order_id}.json"

    def input_bundle_key(self, work_order_id: str) -> str:
        return f"{self.work_order_prefix}{work_order_id}.inputs.json"

    def result_key(self, prepared_result_id: str) -> str:
        return f"{self.prepared_prefix}results/{prepared_result_id}.json"

    def attempt_key(self, attempt_id: str) -> str:
        return f"{self.prepared_prefix}attempts/{attempt_id}.json"

    def marker_key(self, work_order_id: str, attempt_id: str) -> str:
        return f"{self.prepared_prefix}markers/{work_order_id}/{attempt_id}.json"
