# Structural capacity model

v0.9.2 CP03 introduces an **internal, read-only** mathematical capacity model for
the six globally index-addressable PMX structural target collections.

It does not mutate a `PmxDocument`, resize index widths, authorize insertion
execution, add a public service, or promote an insertion capability.

## Inputs

One analysis is defined by:

- a typed `PmxReferenceTargetKind`;
- `current_count`;
- `insert_count`;
- the already-declared `index_width`.

Counts and widths are exact plain integers; booleans are not accepted as integers.
Supported PMX index widths remain `1`, `2`, and `4` bytes.

`result_count = current_count + insert_count`.

## Signedness

Vertex indices are unsigned.

Texture, material, bone, morph, and rigid-body indices are signed.

For a width of `size` bytes:

`maximum_addressable_index = (1 << (size * 8 - signed_bit)) - 1`

where `signed_bit` is `1` for signed targets and `0` for vertex.

`index_addressable_count = maximum_addressable_index + 1`.

## Independent section-count limit

Every PMX section count is also stored as a signed 32-bit integer. Therefore the
section-count limit is independently:

`2**31 - 1`.

The effective result-count limit is:

`min(index_addressable_count, 2**31 - 1)`.

This distinction matters for four-byte indices: an index encoding can mathematically
name more records than the PMX signed 32-bit section-count field can store.

## Evidence semantics

`width_representable` answers only whether the already-declared index width can name
all proposed records.

`count_representable` answers only whether `result_count` fits the signed 32-bit PMX
section-count field.

`representable` is true only when both are true.

`expansion_required` is true only when the current **index width** is insufficient.
It is not a claim that expansion is supported or sufficient. A section-count
overflow can fail with `expansion_required == False`.

Automatic index-width expansion remains out of scope for v0.9.2.

## Authority boundary

`mmd_registry.pmx.validation.validate_pmx_document()` remains the final whole-document
validity authority. CP03 capacity evidence is a preflight mathematical model and
must not compete with document validation.

The CP03 module is intentionally not exported through `mmd_registry.pmx.__all__` or
`mmd_registry.services.__all__`. CP04 will test the exact 1/2/4-byte boundaries
before later insertion checkpoints consume this evidence.
