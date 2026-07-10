# Protocol v2 Schema and Validation

Protocol v2 is isolated under `fs_diloco.protocol` and is not the default
legacy learner/syncer path. It defines immutable Proposal, Commit, Frontier,
Head, ObjectRef, and DropDecision types with exact field sets, explicit version
and enum checks, and canonical round trips.

## Canonical encoding and identities

Identity-bearing JSON uses UTF-8, NFC-normalized strings/keys, sorted keys, and
no insignificant whitespace. Duplicate keys, non-string keys, floats,
NaN/Inf, and unsupported values are rejected. Protocol numeric decisions use
canonical strings such as `float.hex`, not JSON floats.

Proposal IDs are `p-<sha256>` over all identity/content fields except the ID
itself and observational `created_at`. Commit IDs similarly omit `commit_id`
and `created_at`; frontier digests omit their self-digest. Thus timestamps do
not perturb content identity and self-hash recursion is impossible. A supplied
ID that disagrees with the canonical body is a fatal protocol conflict.

## Proposal boundary

A proposal binds run, generation, and model revision; learner session and monotonic sequence
(with one canonical identity per session/fragment/sequence),
fragment and causal base, nonzero local steps/tokens, payload kind/key/tensor
metadata, payload size/SHA-256, and parameter/layout/outer-schema digests. The
run manifest freezes the accepted payload kind and digests.

Validation is layered:

1. strict JSON/schema/canonical identity;
2. run/generation/layout/optimizer/payload-kind contract;
3. identity uniqueness and sequence monotonicity;
4. committed ancestry, exact base-commit/frontier pairing, future-base
   rejection, and global/fragment staleness;
5. namespace containment, file existence, size, and SHA-256;
6. dependency-free safetensors header/key/shape/dtype/offset verification;
7. full finite-value scan in correctness mode.

Errors carry `retryable`, `quarantine`, or `fatal` categories. Missing payloads
may be retried; malformed, mismatched, stale, or non-finite inputs are
quarantined; one identity mapping to different canonical content is fatal. One
bad manifest never needs to become an uncaught scanner exception.

## Namespace and compatibility

`payload_key` is a normalized relative object key. Absolute paths, `.`/`..`,
and any resolved path outside the configured run namespace are rejected before
reading. Protocol v1 manifests can be parsed by the read-only adapter. An
explicit conversion context may construct a v2 object in an isolated new
namespace, but the adapter exposes no authority write and never mixes v1/v2
within one run generation.

Inspect canonical v2 or legacy JSON with:

```bash
python -m fs_diloco.protocol <manifest.json>
python -m fs_diloco.protocol --v1 <legacy.meta.json>
```
