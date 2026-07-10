# 数据流与语义 / Dataflow and Semantics

## 中文

1. syncer 初始化 run manifest、genesis frontier 与 head。
2. learner 从 derived latest 加载 committed checkpoint。
3. learner 写临时 tensor，原子发布 safetensors，再发布 JSON marker。
4. scanner 将 listing 仅当作 candidate discovery；重复、漏项与重排不改变 authority。
5. catalog 对 metadata、因果 base、lineage、path、size、hash、shape、dtype 与 finite
   values 做完整校验；失败项进入 typed quarantine。
6. selection 只存在调用栈/进程内，按 learner oldest-first，最终 proposal IDs 规范排序。
7. syncer 复制 selected proposal objects 到不可变 authority namespace，计算 merge 与
   outer step，准备 params/outer-state/commit/frontier。
8. head CAS 是唯一 commit point。CAS conflict 后丢弃 selection，重新 replay、validate、
   select。
9. CAS 成功后才替换 `RuntimeView` 并生成 latest/metrics exports。

proposal 最多只能出现在一个 committed selection。prepared orphan、marker、heartbeat、
telemetry 或 materialized checkpoint 都不能表示 committed。

## English

1. The syncer creates the run manifest, genesis frontier, and head.
2. A learner loads a committed checkpoint through the derived latest export.
3. The learner atomically publishes a safetensors payload, then a JSON marker.
4. Listings discover candidates only; duplication, omission, and reorder do not
   affect authority.
5. The catalog fully validates metadata, causal base, lineage, containment,
   size/hash, tensor shape/dtype, and finite values; typed failures are
   quarantined.
6. Selection is process-local, oldest-first per learner, and canonically sorted.
7. Selected proposal objects and paired transition outputs are prepared in the
   immutable authority namespace.
8. Head CAS is the sole commit point. Conflicts force replay, revalidation, and
   reselection.
9. Only after successful commit does the process replace `RuntimeView` and
   generate exports.
