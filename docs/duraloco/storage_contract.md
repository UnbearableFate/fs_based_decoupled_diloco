# POSIX/Lustre Semantic Storage Contract

## API 与 key 安全

storage abstraction 提供 immutable create、create-if-absent、conditional replace、verified get/head、
range read、prefix listing 和 per-object batch delete status。所有 key 是隔离 root 下的 canonical
relative POSIX path；absolute/alias/dot segment/control/backslash/symlink traversal 和内部 lock namespace
都被拒绝。

listing 只用于 discovery 与 GC inventory，不参与 head read、CAS success 或 recovery prefix 选择。
H0 后 `list_prefix(prefix)` 只遍历目标 prefix subtree；`head`、listing 和 immutable-create 的幂等检查
读取有 checksum 的 bounded envelope header，不读取 payload。`get`/`verified_get` 仍完整验证 payload。

当前 `PosixStorageBackend.range_get` 仍调用完整 `get` 后切片，不应声称 true range I/O；这是 P08 的
明确优化项。

## Envelope、原子性与 CAS

每个可见文件包含 opaque version、previous version、payload size/SHA-256 和 payload。mutation 使用
稳定 per-key advisory `flock`、同目录 temp、flush+`fsync(file)`、immutable link 或 atomic replace，
并在能力可用时 `fsync(parent directory)`。

随机 opaque version 防止 ABA。lost-response retry 只有在同一 request ID、当前 envelope 直接前驱
等于 caller expected version、且 new bytes 相同的情况下才幂等成功；不同 client 的 request ID 不同，
同 expected version 的 race 最多一个 winner。没有 request ID 时 ambiguous stale call fail closed。

lock inode 不是 ownership。进程退出时内核释放 `flock`；takeover 不删除或按 mtime 过期 lock file。

## Integrity 与 capability

短读、envelope/header checksum 不符、payload hash/size 不符、malformed object 都产生 typed integrity
failure。missing、immutable conflict、CAS conflict、invalid key、lock timeout、capability missing 和 OS
I/O failure 分开处理；EIO/ESTALE 可标记 retryable，permission/quota/no-space 不自动无限重试。

authority root 启动前必须验证 cross-node advisory locking。capability report 记录 filesystem/mount、
Lustre stripe、atomic replace、directory fsync、immutable conflict、verified read、range behavior、CAS race
和 cross-node lock evidence。H0 两节点 probe 在不同 host 上证明持锁时 contender 阻塞、释放后获取。
无法证明跨节点排他时 authority fail closed。

directory fsync 只支持已探测的 process/OS crash 模型，不等于承诺永久存储丢失、controller failure
或任意 parallel-filesystem 灾难下的物理 durability。

## Lifecycle I/O 计数

H0 lifecycle inventory 将 header reads 与 payload reads 分开计数。最终 D8 五次 inventory 的 payload
bytes read 都为 0，即使 logical inventory 从 9.21 GB 增长到 40.82 GB；这只说明 inventory/reachability
metadata path 没有读取大 payload，不代表 strict replay 省略 payload verification。

payload-corrupted unknown object 仍必须可被 header inventory 发现，verified get 失败，并因 unknown/
quarantine 规则免于 GC。不能为了性能把“无法验证”解释成“不可达”。
