# Lifecycle：Snapshot、Reachability、Capsule 与 GC

## Snapshot compaction

snapshot 是某个 committed head/frontier 的 immutable、self-verifying projection，包含 covered state、
causal bases、control request summary、embedded verified objects 和必要的 numel/ObjectRef metadata。
它只有在 fenced owner 提交 snapshot-pin transition 后才是恢复候选。

恢复始终验证 snapshot+suffix 与 strict replay state digest 相等。newest snapshot 损坏时尝试下一个
valid base；都无效则完整 replay。系统至少保留两个 valid restore base，避免 GC 后只剩单点恢复。

## Explainable reachability

reachability 以 verified committed replay 为起点，listing 只提供 inventory。report 为每个 root/edge
记录 retention reason，并可解释目标 object 的 root path。主要 root class 包括：

- current head、run manifest、尚未由两个 snapshot base 覆盖的 committed ancestry；
- retained snapshot 和 live suffix commit/frontier/params/outer/proposal；
- active FWO、input bundle、PFR、attempt/failure evidence；
- same-digest loser 与 divergent-result blocker evidence；
- membership、revision/grace-eligible proposal 与 payload-before-marker object；
- lifecycle pin、acknowledgement、exact capsule、近期 GC mark/request/result；
- invalid/corrupt quarantine 与无法识别的 future-schema object。

只有已知 collectable class、不可达且调用方提供 grace 已过的 immutable evidence 才能成为 candidate。
unknown object 默认保护；坏 metadata 也不能直接删除。

## Exact learner capsule

capsule 在一致性点捕获 model、inner optimizer、scheduler/scaler presence/state、CPU/CUDA RNG topology、
data cursor、interval/open state、frontier、session/sequence 和 pending proposal IDs。所有组件先按内容寻址
写入，再写 manifest，最后写 discovery marker；response loss 下 publication 可幂等恢复。

restore 要求每个组件存在并匹配 ObjectRef、capsule frontier 与当前 expected frontier 一致、RNG/data
source 可恢复，并创建新 learner session/monotonic sequence。缺字段或只保存部分私有 state 的对象
不能声称 exact。synthetic fixture 已证明 bitwise continuation；真实 D8 中 whole-host loss 的实验动作是
membership removal，不应误写成 automatic exact learner reintegration。

## GC safety

`build_reachability` 产生 explainable inventory；`create_gc_mark` 以当时 head/fencing/membership 和 candidate
集合创建 immutable dry-run mark。apply 前重新计算 reachability；head advance、新 pin、对象重保护或
mark mismatch 都使 apply 失效。delete 使用 request/result identity，能够处理 response loss 和 partial
apply，不把 missing-after-delete 误判成新成功。

当前 CLI 对 real authority namespace 只支持 reachability 与 dry-run mark：

```bash
python -m fs_diloco.lifecycle_cli \
  --storage-root <authority-root> --run-id <run> --run-generation 0 \
  reachability --explain <key>

python -m fs_diloco.lifecycle_cli \
  --storage-root <authority-root> --run-id <run> --run-generation 0 \
  gc-mark --output <mark.json>
```

destructive `gc-apply` 的 argparse 只接受 `--namespace synthetic`，还要求 approval token 和 request ID。
因此“GC 已实现”指对象图、mark/apply protocol 与 synthetic destructive tests 已实现，不指 real run
已授权物理删除。

## Lifecycle cadence

floating committer 可按 `--lifecycle-cadence N` 运行 snapshot、strict equivalence、reachability 与 GC
dry-run。长 lifecycle substage 在 worker 中执行，同时 control thread 按 cadence 续租；substage error、
renewal failure、ownership change 或 expired lease 都 fail closed，失去 owner 后不能提交 lifecycle result。

H0 D8 的五次 lifecycle 分别耗时 34.33、39.30、49.34、58.40、68.42 秒，inventory payload reads
均为 0。时间随 committed/inventory 增长仍明显上升，属于 P08/P11 需要继续 profile 的性能信号。
