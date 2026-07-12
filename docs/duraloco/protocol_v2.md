# Protocol v2：Schema、Identity 与 Validation

Protocol v2 是当前 DuraLoCo authority 路径，不再只是隔离的未来 schema。实现位于
`fs_diloco/protocol/`，production log、learner publication、distributed work order/result、membership
和 lifecycle 对象都使用 canonical identity 与 typed validation。

## Canonical encoding

identity-bearing JSON 使用 UTF-8、NFC 字符串/键、排序键和无无意义空白的 canonical form。重复键、
非字符串 key、未声明字段、非法 enum、NaN/Inf 和 identity 中的普通 JSON float 被拒绝；协议数值
使用 canonical string（例如 `float.hex`）。

content ID 由除自身 ID 与明确 observational timestamp 外的 canonical body 计算。一个 ID 映射到
两个不同 canonical body/digest 是 fatal conflict，不能 quarantine 后继续。`ObjectRef` 完整 identity
为 `(key, sha256, size)`；只比较路径或 hash 都不足够。

## RunSpec 与隔离

每个 run generation 的 immutable manifest 冻结：run/generation、payload/codec version、parameter
和 fragment layout digest、outer optimizer/schema、numeric/weighting contract、coordination protocol、
revision-zero membership、replication factor 与 execution backend digest。run ID 和 generation 的
对象不得交叉引用。

相对 object key 必须是 canonical POSIX spelling，并位于该 run namespace。absolute path、`..`、`.`、
重复分隔符、反斜杠、控制字符、symlink escape 或声明 key 与实际 key 不一致都在读取 payload 前
拒绝。

## Proposal validation pipeline

Proposal identity 绑定 run/generation/model revision、learner/session/sequence、fragment、causal base、
local interval/steps/tokens、payload kind/key/tensor metadata、size/SHA-256、layout/optimizer digest。

进入 eligibility 前依次验证：

1. strict schema、canonical round trip 与 ID；
2. RunSpec、generation、layout、optimizer、dtype/payload-kind；
3. session/fragment sequence 唯一性与 lineage 单调性；
4. base commit/frontier/fragment version、committed ancestry、future-base 和 staleness；
5. namespace、存在性、ObjectRef size/SHA-256；
6. safetensors header、key、shape、dtype、offset；
7. correctness mode 下的完整 finite-value scan。

只有 full validation 且 `eligible=true` 的 typed report 可参与 selection。missing/incomplete 可以 retry；
malformed、stale、mismatch、non-finite 被 quarantine；identity conflict 或 corruption suspicion fail closed。

## Distributed transition objects

FWO 绑定 parent commit/frontier、selected proposal 与 canonical weights、expected output、membership
revision、primary/backup ownership、fencing epoch、redundancy policy、backend/layout/optimizer digest。
input bundle 只引用经验证对象。

PFR 包含新 params/outer-state ObjectRef、work order/attempt/executor identity 和 resource evidence，采用
payload-first、marker-last 发布。committer 必须重新验证 marker、manifest、所有 ObjectRef 与 FWO
context。同 backend 下 duplicate attempts 的 semantic result 必须 exact；不同结果会阻止提交。

Commit/Frontier/Head 把 selection、numeric decision、paired output、membership 和 control transition
串入同一 parent-linked chain。head CAS 是唯一 linearization point。

## Compatibility

v1 adapter 只读解析历史 manifest；转换必须进入隔离的新 generation，不能把 v1/v2 对象混在同一
authority prefix，也不能写入旧 authority。检查 manifest：

```bash
python -m fs_diloco.protocol <v2-manifest.json>
python -m fs_diloco.protocol --v1 <legacy-manifest.json>
```

早期 central syncer path 仍在代码库中，但不能弱化 Protocol v2 identity、validation 或 head authority。
