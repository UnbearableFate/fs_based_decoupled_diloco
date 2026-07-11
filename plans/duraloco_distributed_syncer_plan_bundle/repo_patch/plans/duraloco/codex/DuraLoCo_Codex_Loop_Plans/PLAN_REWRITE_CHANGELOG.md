# DuraLoCo Plan Rewrite Changelog

## Purpose

本次改写把 P06 后的路线从“继续强化 dedicated central syncer”改为“先冻结中心式 reference semantics，再迁移到 learner-hosted distributed fragment syncer”。历史 P00–P06 verdict保留；P07–P12 和可选 P09 按分散式拓扑重写。

## v3.1 current-repository audit corrections

审查时当前仓库已在`main` `06e3ca2`归档P06，实际验收只有P06-A01–A20。
v3.0把CRS trace追加为P06-A21–A25会与STATE/report/Checker冲突，现已撤销；P06A从
archive tip负责characterization。新增`CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md`记录完整
审查依据。

同时完成以下修订：

- P06A复用现有`ProposalCatalog`、`ProductionTransactionalLog`、`outer_optim`等边界，
  并要求改动后的同commit C1→C2→C9，不再复用旧terminal pass；
- P06B以新run generation/protocol引入membership/FWO/PFT，不原地升级P06 generation；
- 分离PFT canonical result与attempt/telemetry identity，避免arrival order进入authority；
- 区分same-backend exact content identity与CPU/GPU tolerance-based numeric equivalence；
- required route改为P06C→P07→P08→P10，避免P07/P08并行修改尚未冻结的shared schemas；
- P07增加五个顺序子门，P08 bundle改为profile-triggered conditional gate；
- P10改为shadow-first、system-only enforcement first；algorithm-affecting actions需要新
  generation/committed identity/quality evidence，允许诚实`not_qualified`结论。

## Route change

旧路线：

```text
M00 → P05 → P06 → (P07, P08) → P10 → P11 → P12
```

新路线：

```text
M00 → P05 → P06 → P06A → P06B → P06C → P07R → P08R → P10R → P11R → P12R
```

## New stages

- **P06A**：拆分 syncer orchestration 与 pure kernels；central reference equivalence。
- **P06B**：learner-hosted LFE、FWO/PFT、floating committer、replication factor 1；D8 无专用 syncer。
- **P06C**：在P06B committed membership/ownership上增加replication factor 2、hedged execution、reconfiguration及owner/committer/whole-node failover。

## Rewritten stages

- **P07R**：reachability/GC 增加 FWO、PFT winner/loser、ownership epoch、response-loss evidence roots。
- **P08R**：优化对象从 central syncer改为LFE pipeline；新增 CPU/NUMA/GPU interference、bounded concurrency和bundle-equivalence。
- **P10R**：SACC扩展为同时控制quorum/grace、in-flight/bundle、hedge、replication activation和learner-host资源。
- **P11R**：主验收由C9（1S+8L）改为D8/D8-R2（8 learner nodes，无专用syncer）；C9只作reference baseline。
- **P12R**：正式实验必须比较C9、P05 active/standby、D8、D8-R2和controller modes，并报告node/GPU allocation、interference、fault goodput和quality。
- **P09R**：若未来启用object-store backend，也必须沿FWO/PFT和D8主路径实现。

## Normative additions

- `DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md`
- `RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md`
- 更新后的 templates 与 build script

## Applying to repository

1. 用本包中的 `DuraLoCo_Codex_Loop_Plans/` 替换仓库同名目录；保留仓库外部的 `plans/duraloco/STATE.yaml`、`DECISIONS.md`、`BLOCKERS.md` 实际运行状态。
2. 用 `repo_patch/scripts/agent/build_duraloco_master.py` 替换仓库对应构建脚本。
3. 运行：

```bash
python3 scripts/agent/build_duraloco_master.py
python3 scripts/agent/build_duraloco_master.py --check
(cd plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans && sha256sum -c SHA256SUMS.txt)
```

4. 当前仓库P06已完成，不追加或重跑P06-A21–A25。从archive commit `06e3ca2`启动P06A；
   先完成characterization/decomposition，不要直接进入P07/P08。
5. 不要自动merge main；按现有Maker–Checker和Miyabi纪律创建新milestone commit。
