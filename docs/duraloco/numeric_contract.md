# DuraLoCo Numeric Contract

## Modes

Reference/audit mode uses canonical proposal order, float64 scalar weight
normalization and accumulation, deterministic pure-CPU transition code, and
canonical hexadecimal float serialization in decision records. Given equal
inputs and implementation digest, metadata and state digests must be bitwise
stable.

Production/performance mode may use FP32 accumulation, GPU streaming reduction,
BF16/FP16 payloads, and fused kernels. It must preserve the committed inputs,
selection, weights, output/outer-state pairing, and implementation digest.
Numerical comparison is tolerance-based and cannot be described as bitwise
cross-hardware replay.

## Reference formulas

Token/staleness weights are computed in float64, normalized in canonical
proposal-ID order, and recorded using `float.hex`. Weighted proposal reduction
uses that same order. SGD, momentum, Nesterov, and AdamW follow the formulas in
the existing `fs_diloco.outer_optim` implementation; weight decay placement,
epsilon, bias correction, and step counter are part of the implementation
identity.

For P02 vectors, exact digest equality is required for repeated execution on
the same Python implementation. Comparisons against the legacy Torch path use
`abs <= 1e-7 + 1e-6 * abs(reference)` for FP32 results unless an individual
test records a stricter bound. BF16/FP16 performance paths receive separate,
explicit tolerances in later phases. NaN or infinity is always a hard failure
in correctness suites.

## Boundaries

Global optimizer replay does not imply identical learner execution. Exact
learner trajectory additionally requires consistent inner optimizer,
scheduler/scaler, RNG, data cursor, adoption event tape, code, and hardware
behavior. A test result must state whether it proves metadata determinism,
global numeric equivalence, or full learner continuation.
