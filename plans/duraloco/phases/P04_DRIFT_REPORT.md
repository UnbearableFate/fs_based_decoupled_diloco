# P04 Baseline Drift Report

- Planning baseline: `codex/fs-diloco-miyabi` at
  `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- Actual base: completed P03 branch `codex/duraloco-p03-posix-storage` at
  `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- Required drift: P01 added frozen Protocol v2 schemas, P02 added the
  deterministic transition oracle, and P03 added the checked memory/POSIX
  semantic storage contract required by P04.
- User work: unrelated untracked historical artifacts and a P00–P02 PBS file
  were observed and left untouched.
- Action: build P04 only on the completed phase chain. Do not reset to the
  planning baseline and do not change legacy learner/syncer defaults.

## 中文

- 规划基线：`codex/fs-diloco-miyabi`，提交
  `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- 实际基线：已完成的 P03 分支 `codex/duraloco-p03-posix-storage`，提交
  `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- 必要漂移：P01 已冻结 Protocol v2 schemas，P02 已增加确定性 transition
  oracle，P03 已增加 P04 所依赖且经复核的 memory/POSIX 语义存储 contract。
- 用户工作：已观察到无关的历史未跟踪 artifacts 和 P00–P02 PBS 文件，均未改动。
- 处理：只在已完成的阶段链上实现 P04，不 reset 到规划基线，也不改变旧
  learner/syncer 的默认路径。
