# 快速开始

## 1. 先确认所在节点

Miyabi login node 是 control plane，只能编辑、查看、静态检查、`qsub/qstat` 和读取日志。
训练、模型加载、torch/CUDA/transformers import、dataset preprocessing、pytest runtime、
`torchrun` 和 `mpirun` 必须进入 PBS compute allocation。

```bash
hostname
printf 'PBS_JOBID=%s\n' "${PBS_JOBID:-}"
printf 'PBS_NODEFILE=%s\n' "${PBS_NODEFILE:-}"
```

没有有效 `PBS_JOBID`/`PBS_NODEFILE` 时，不要尝试 runtime smoke。

## 2. 查看状态并选择路径

```bash
git status --short --branch
sed -n '1,220p' plans/duraloco/STATE.yaml
sed -n '1,220p' docs/status.md
```

当前 DuraLoCo 分布式资格路径使用：

- `configs/duraloco_milestone_gpt2_9node_50x10.yaml`：GPT-2/WikiText-2，50 local × 10 global；
- `scripts/miyabi/run_duraloco_p07_d1_r2.pbs`：1-node real D1；
- `scripts/miyabi/run_duraloco_p07_d2_r2.pbs`：2-node tiny failover；
- `scripts/miyabi/run_duraloco_p07_d8_r2.pbs`：9-node allocation、8 learner/runtime host。

`run_1node_debug.pbs`、`run_2node_debug.pbs`、`run_9node_*` 和
`scripts/local/run_tiny_2proc_smoke.sh` 是较早的 central-syncer/reference smoke。它们可以用于
局部调试，但不能替代 P07/H0 的 distributed executor + floating committer 资格证明。

## 3. 登录节点静态门禁

```bash
bash -n scripts/miyabi/*.pbs scripts/miyabi/*.sh scripts/local/*.sh
.venv/bin/ruff check fs_diloco tests scripts/agent
.venv/bin/python scripts/agent/check_research_contract.py --root "$PWD"
.venv/bin/python scripts/agent/check_docs.py --root "$PWD"
.venv/bin/python scripts/agent/check_no_embedded_database.py --root "$PWD"
.venv/bin/python scripts/agent/check_phase_state.py plans/duraloco/STATE.yaml
git diff --check
```

这些命令不加载训练 runtime。不要在 login node 为了“多验证一点”追加 pytest 或 torch import。

## 4. 提交 PBS

先阅读目标脚本顶部的 required environment variables。DuraLoCo 验证脚本通常要求显式提供：

```text
EXPECTED_COMMIT   允许执行的干净 Git commit
RUN_ID            唯一 run namespace
ARTIFACT_ROOT     本次证据输出目录
STORAGE_ROOT      authority/storage 根目录
```

D8 还可能要求上一阶段 factor-one report。实际变量以脚本中的 `${VAR:?message}` 为准。脚本的
`#PBS -W group_list` 必须是有效 group；当前仓库使用 `xg24i002`，复制脚本到其他项目时必须改成
真实 group。

运行顺序固定为：

```text
1-node static/unit + D1
        ↓
2-node lock/correctness + D2-R2
        ↓
9-node allocation / D8-R2
```

不允许用 9-node PASS 反推未运行的 1/2-node gate，也不允许非瞬态 9-node terminal failure 后原样
立即重投。见 [operations.md](operations.md)。

## 5. 检查结果

对现有 run 的 derived summary：

```bash
python -m fs_diloco.analysis <shared-run-root> --json
```

对 DuraLoCo authority 做完整 replay/verify（在安全 runtime 节点）：

```bash
python -m fs_diloco.log.inspect_cli verify \
  --root <shared-run-root>/authority \
  --run-id <run-id> \
  --generation 0
```

不要只看 `latest.json`、`stop.json` 或最后一行 telemetry 判定成功；必须同时核对 PBS exit、阶段
report、authoritative head/stop transition、manifest/checksum 和 acceptance gate。
