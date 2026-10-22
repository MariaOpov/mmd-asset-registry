# v0.9.5.11 — Smart Morph first slice (internal/read-only)

## Contract and source

This first-slice implementation is governed by **FROZEN-CP02-R2** (SHA-256 `a1ba9ed86fa0bd0457ad88bac0044597576763f171d4b5a1358dbea019e5cfdd`). The authority is the released, deterministic exact-alias Smart Part detector and the existing PMX reader/catalog. Permanent Rules SHA-256 is corrected via the CP03B erratum to `df2091a05a58879bae365f8a53f080c603efcb7b9862ca8a272d479e6b678e87`.

Private function `mmd_registry.services._smart_morph_inspection.inspect_smart_morphs(source_bytes: bytes)` returns a frozen/slotted, source-bound `SmartMorphInspection`. The input must be **exact bytes**, not a path or mutable buffer. The function parses once with the existing PMX reader, inventories all existing morph types 0 through 10 in ascending source order, and returns exactly two semantic capability descriptions in the order **smile, blink**.

The only positive descriptive eligibility:

- **smile**: exact smile/笑顔/笑い alias on a direct morph source, part kind FACE.
- **blink**: exact blink/まばたき alias on a direct morph source, part kind EYES.
- Exactly one eligible candidate with morph type **1 (vertex)** or **2 (bone)** and **at least one typed offset**; no same-source semantic conflict or source mismatch.

Morphs of any other type (group, UV/additional UV, material, flip, impulse) remain inventoried but cannot receive a positive first-slice capability. Generic `face`, `eyes`, `eye`, `wink`, or other related aliases do **not** establish a smile/blink slot. No fuzzy or substring inference is performed.

### Fail-closed status precedence

0. Invalid PMX bytes: propagate the existing reader diagnostic; no success record.
1. Source/catalog mismatch: `blocked / source_evidence_mismatch`.
2. Same-source recognized semantic conflict: `blocked / same_source_exact_conflict`.
3. Two or more distinct exact slot source indices: `blocked / multiple_exact_morph_candidates`.
4. No candidate: `unsupported / no_exact_morph_evidence`.
5. One candidate with type outside {1,2}: `unsupported / morph_type_out_of_scope`.
6. One eligible type with empty offsets: `unsupported / empty_morph_offsets`.
7. Single type 1/2 candidate with offsets: `supported / exact_morph_evidence`.

All evidence originates from the detector's **pre-filter candidate traces**, including local and universal source fields on conflicts. Exact full-trace deduplication and the detector's canonical sort key apply; candidate source indices are sorted unique integers. Model identity is bound to the SHA-256 of the exact PMX bytes and is private to the in-memory result.

### What `supported` does NOT mean

`SUPPORTED` is structural/semantic presence **only**. It does not prove visible displacement, animation effect, morph-weight activation, suitability for geometry editing, preview/apply permission, or safe automatic retargeting. This release slice has **no** morph writer, deformation algorithm, weight setter, edit plan, preview, apply, public root export, new CLI option or version bump. Do not log real model bytes, paths, source hashes or names in QA evidence. Tests use programmatic synthetic PMX only.

### Test gates and ownership

Session A files are exactly the two private modules, the two `tests/test_v09511_morph_core_*.py` modules and this document. Session B owns separate QA paths; A does not modify them. Use Python 3.12 `unittest` and the repository `.venv`. No third-party installation is needed for this slice. Git staging/commit/push/PR/release require separate authorization.
