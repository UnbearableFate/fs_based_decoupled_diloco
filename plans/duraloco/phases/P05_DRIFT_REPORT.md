# P05 Baseline Drift Report

## English

- Planned base: `codex/duraloco-m00-sqlite-free-rebase` at
  `89ae48aae5956b09fc6685074d3ea0eaea36b816`.
- Actual base: the same branch at
  `92acc3af0c2e80951dfcbf20c738841428a8b906`.
- Relationship: the planned base is an ancestor of the actual base. The P05
  feature branch was fast-forwarded without rewriting or discarding history.
- Drift content: post-M00 execution-contract hardening, schema-v2 evidence
  tooling, corrected P05/P06 acceptance plans, M00 implementation lessons, and
  planning checksums. No production optimizer authority or tensor runtime code
  changed after the corrected M00 archival tip.
- Decision: use `92acc3a` as the P05 actual base. Retain `89ae48a` as the
  normative M00 planning basis and runtime/evidence lineage.

## 中文

- 计划基线：`codex/duraloco-m00-sqlite-free-rebase` 的
  `89ae48aae5956b09fc6685074d3ea0eaea36b816`。
- 实际基线：同一分支的
  `92acc3af0c2e80951dfcbf20c738841428a8b906`。
- 关系：计划基线是实际基线的祖先。P05 feature branch 通过 fast-forward
  前进，没有改写或丢弃历史。
- 漂移内容：M00 后执行契约强化、schema-v2 evidence 工具、修正后的 P05/P06
  验收计划、M00 实施经验和计划 checksum。corrected M00 archival tip 之后没有
  修改 production optimizer authority 或 tensor runtime 代码。
- 决策：以 `92acc3a` 作为 P05 实际基线；`89ae48a` 继续作为 M00 规范计划基线和
  runtime/evidence lineage。
