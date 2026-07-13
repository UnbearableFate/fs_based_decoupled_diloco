# 数值与选择契约

## Deterministic selection

候选只有通过完整 validation 才能进入 eligibility。当前 frozen policy 是 `oldest_pending`，最大/最小
quorum 和 staleness 由 RunSpec/config 冻结；同一 learner 每个 transition 最多选择一个 proposal，
已 consumed 或 terminally dropped proposal 不再贡献。

选择、drop decision 和 weights 都进入 canonical commit identity。listing 的顺序、重复观察、延迟漏项
和 CAS conflict 后的重扫不能改变同一 authoritative input 上的 decision identity。

## Canonical weights

Protocol v2 staleness 系数固定 `lambda=0.2`。token/staleness 权重先由 reference policy 计算，再以
canonical numeric string 编码；普通 JSON float 不进入 identity。commit 保存 selected proposal、
local token/step、base/staleness 与最终 canonical weight，replay 独立重算。

## Tensor 与 dtype

proposal transport 可用 bfloat16 safetensors；aggregation 和 committed production params/outer state 在
reference path 中以 float32 计算/编码。outer optimizer step tensor 可合法使用 int64，而 proposal
payload 只允许 RunSpec 声明的浮点 tensor contract。safetensors header、唯一 tensor key、shape、dtype、
offset、size、SHA-256 和 finite values 均在 eligibility/commit 前验证。

full-vector (`fragment_id=0`) 与 balanced-tensor fragments 使用同一 transition contract。每个 fragment
的 params 与 outer state 必须由同一 commit 产生；fragment scheduler 目前是 deterministic
`round_robin_global`，每次 update 只处理一个 fragment。

## Outer optimizer

实现包含显式 flat-vector SGD、momentum/Nesterov 和 AdamW-style outer optimizer。optimizer name、lr、
momentum/betas/eps/weight decay、state schema 和 backend digest 被 RunSpec/FWO 绑定。LFE 输出由
reference adapter/oracle 检查；同 backend 的 redundant attempt 必须产生相同 semantic result。

“deterministic”限定在相同 canonical input、declared numeric mode、execution backend 和实现 commit。
它不承诺不同 PyTorch/CUDA/CPU 架构、线程归约顺序或未来 backend 间 bitwise equality。

## 当前性能边界

numeric contract 不要求当前实现已经 streaming。LFE 仍加载完整 params/outer/proposal tensors，并可能
产生额外 float/materialization/copy；`range_get` 也不是 true range I/O。P08 可以改变 I/O/reducer
实现，但必须保持 canonical serial oracle、transition identity 或通过显式新 schema/generation 处理
不兼容变化。
