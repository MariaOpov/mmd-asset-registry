# Public API policy

This document defines the public package boundary carried from v0.9.0 into
v0.9.1. The release retains read-only reference analysis and certified
structural preview while additively exposing a bounded structural execution
service over the already-verified safe-output kernel. Raw structural writer
internals remain non-public.

## Public surface

Public names must be deliberately listed in the owning module's `__all__`.
They must be typed, deterministic, side-effect-controlled, independent from
`argparse.Namespace`, and usable without printing, exiting the process, or
assuming the repository root is the current directory.

The current public namespaces are:

- `mmd_registry`, whose only root export is `__version__`;
- `mmd_registry.capabilities`, for the immutable current-support manifest and
  canonical `get_capabilities()` entry point listed in its `__all__`;
- `mmd_registry.diagnostics`, for immutable service operation, code,
  diagnostic, exception-wrapper, and safe error-adapter types in its `__all__`;
- `mmd_registry.pmx`, for the typed PMX document, reader, validation, writer,
  and round-trip surface listed in its `__all__`;
- `mmd_registry.pmx.editing`, for the bounded declarative editing surface
  listed in its `__all__`;
- `mmd_registry.services`, for typed CLI-independent document, validation,
  reference-analysis, bounded editing, structural preview/execution, and
  capability use cases listed in its `__all__`.

Future public entry points must be exposed through an intentional documented
namespace and an explicit `__all__`; importing a module from the package does
not by itself make that module public. The service namespace delegates to the
existing v0.8 safety pipeline and does not expand editing authority.

## Capability surface

`mmd_registry.capabilities` publicly exports `PmxCapabilityManifest`,
`PmxRoundTripContract`, and `get_capabilities`. The returned manifest is frozen,
slotted, deterministic, independent from private runtime configuration, and
contains only the PMX versions, encodings, index widths, deform and morph
types, round-trip contract, texture portability, soft-body support, the three
edit operations already implemented by v0.8.5, and the reviewed structural
contract. The canonical v0.9.1 manifest reports preview and bounded structural
write support, the six supported target kinds, and `reference_safe_execution`.
The dataclass constructor keeps its v0.9.0 preview-only defaults so callers that
construct the manifest with the old argument shape remain compatible.

Absence from the manifest means unsupported; the API does not imply model
creation, VMD editing, plugin loading, unrestricted physics editing, or any
future edit operation. The former `get_pmx_capability_manifest()` name remains
directly importable for compatibility, but is not a canonical `__all__` export.

## Diagnostic surface

`mmd_registry.diagnostics` exposes a presentation-independent failure boundary
for the document, validation, and edit services that already exist. A
`PmxServiceDiagnostic` is frozen, slotted, deterministic, JSON-ready, and uses
the bounded `PmxServiceOperation` and `PmxServiceDiagnosticCode` vocabularies.
`PmxServiceError` carries exactly one such diagnostic without printing,
terminating the process, or assigning an exit code.

`diagnostic_from_service_error()` converts only allowlisted stable fields from
known PMX failures. Filesystem paths, arbitrary exception text, exception
representations, and unexpected implementation details are replaced with
coarse safe messages. Existing domain exception types and CLI diagnostics are
not removed or redirected.

The operation and code vocabularies describe current behavior only. They do
not promise model creation, VMD editing, plugin loading, unrestricted physics
editing, or future edit operations.

The v0.9 reference-analysis service adds the `analyze_references` and
`analyze_reference_node` operations. Argument and unexpected implementation
failures use the same redacted service diagnostic boundary as the existing
document, validation, and edit services.

## Document service

`mmd_registry.services.load_document()` accepts a filesystem path or a
caller-owned seekable binary stream and returns the existing typed
`PmxDocument`. Paths opened by the service are closed before return; streams
supplied by callers remain owned by their callers. Malformed data, file I/O,
invalid arguments, and unexpected implementation failures are reported as
`PmxServiceError` values for the `load_document` operation.

`inspect_document()` accepts a typed document and returns immutable
`PmxDocumentMetadata` containing its version, encoding, names, and comments.
Invalid inputs use the corresponding `inspect_document` diagnostic operation.
Neither service prints, exits, loads the CLI, assumes the repository root, or
exposes a wrapped implementation exception as public failure context.

The direct `mmd_registry.pmx.load_pmx()` domain API and its exception behavior
remain available for compatibility. This service does not change the PMX
validation pipeline or add editing authority.

## Validation service

`mmd_registry.services.validate_document()` accepts the existing typed
`PmxDocument` and returns an immutable `PmxDocumentValidationResult`. Its
`is_valid` property and `to_dict()` method provide deterministic typed and
JSON-ready views. Issues retain the existing immutable `PmxValidationIssue`
section, record index, field, and reason fields without rendering or assigning
an exit code.

The current core validator is deliberately fail-fast, so a valid result has no
issues and an invalid result contains the first issue found by the established
deterministic validation order. Document invalidity is a normal result;
invalid service arguments and unexpected implementation failures use a
redacted `PmxServiceError` for the `validate_document` operation.

The direct `mmd_registry.pmx.validate_pmx_document()` API retains its existing
`PmxValidationError` behavior for compatibility. The service does not print,
exit, load the CLI, alter edit execution, or add any edit operation.

## Reference-analysis service

`mmd_registry.services.analyze_references()` accepts an existing typed
`PmxDocument` and returns one immutable `PmxReferenceAnalysisResult`. The
service deliberately does not prevalidate the document: semantically invalid
but structurally parsed documents must remain analyzable so dangling,
out-of-range, and unsupported conditional reference evidence is observable.

The result retains the deterministic raw reference graph and the stable
structured diagnostics derived from it. Its `relationship_counts` property
summarizes valid extracted edges by stable relationship ID; `is_clean` and
`to_dict()` remain deterministic and JSON-ready. Public result construction
fails closed if supplied diagnostics do not exactly match the graph-derived
diagnostics. Analysis is read-only and does not write files, normalize indices,
infer repairs, or mutate the document.

`analyze_reference_node()` accepts one existing analysis snapshot plus a typed
`PmxReferenceNode` and returns the conservative direct `PmxReferenceImpact`
computed from that same snapshot. It does not reparse or re-extract the model.
Missing nodes and invalid service arguments fail through `PmxServiceError`
using the `analyze_reference_node` operation.

The public service namespace also exposes the reference node/target kind,
diagnostic, and impact types needed to consume these two operations without
depending on CLI or presentation modules. Reference analysis itself remains
read-only; v0.9.0 exposes structural intent only through the separately bounded
structural preview service below.

## Structural preview service

Version 0.9.0 introduced the deliberately narrow preview boundary.
`PmxStructuralCollectionEdit` describes an ordered subset of existing indices
for one supported target collection, `PmxStructuralPreviewRequest` combines
non-duplicated collection edits, and `preview_structural_edit()` returns an
immutable `PmxStructuralPreviewResult` only after the structural intent passes
certification and fresh reference-integrity analysis.

The released v0.9.0 capability vocabulary for this preview-only boundary was
`structural_write=False` and `structural_contract="reference_safe_preview"`.
Those literals remain documented as compatibility history; the authoritative
current capability is the v0.9.1 execution contract below.

### Structural execution service (v0.9.1)

v0.9.1 additively exposes `PmxStructuralEditRequest` as the same frozen request
contract and `apply_structural_edit(input_path, output_path, request,
*, overwrite=False)` as the reviewed execution boundary. Execution returns a
`PmxStructuralExecutionResult`; the raw `PmxStructuralWriteResult`, transform
intent, remap primitives, serializer, and filesystem commit hooks remain
implementation details and are not exported through canonical public namespaces.

The supported public structural target kinds are `vertex`, `texture`,
`material`, `bone`, `morph`, and `rigid_body`. Preview and execution may reorder
or delete existing records when dependent references remain valid or are
coordinately remapped. New indices/insertion are not authorized, boolean values
are never accepted as indices, and changed transforms fail closed on opaque
trailing data, invalid references, unsupported states, or index-width capacity
violations.

Execution resolves source/destination safety first, captures one source snapshot,
builds the request-derived intent against exactly that parsed snapshot, then
reuses the certified preview -> serialize -> reparse -> recertify -> semantic
equality pipeline before atomic publication. The source identity and SHA-256 are
rechecked immediately before publication, and overwrite applies only to a
separate destination. No in-place structural editing is exposed.

The execution service is imported lazily so merely importing
`mmd_registry.services` does not load the structural writer. Expected failures
cross the structured service diagnostic boundary under `apply_structural_edit`;
CP17 may add richer provenance without changing this stable service shape.

The capability manifest is authoritative for the current release:
`structural_preview=True`, `structural_write=True`, and
`structural_contract="reference_safe_execution"`.

## Edit service

`mmd_registry.services.preview_edit()` accepts immutable source bytes and an
existing typed `PmxEditPlan`. It returns the established immutable
`PmxEditPreview` only after parse, plan application, serialization, reparse,
semantic equality, and source-integrity verification complete. Preview never
writes a file.

`apply_edit()` accepts distinct input and output paths, the same typed plan,
and an explicit overwrite flag. It delegates to the existing safe-output
pipeline, including path and alias policy, source identity and hash checks,
temporary-file verification, destination-state rechecks, and atomic commit.
It returns the existing immutable `PmxEditWriteResult`; the input remains
unchanged and in-place editing remains unsupported.

Both services report expected and unexpected ordinary failures as redacted
`PmxServiceError` values for their own operation. Process-control exceptions
are not converted. The CLI adapts expected service diagnostics to its legacy
presentation and exit-code contract, while direct
`mmd_registry.pmx.editing.dry_run_pmx_edit()` and `write_pmx_edit()` calls retain
their existing domain exceptions.

The edit surface remains exactly `set_model_info`, `set_texture_path`, and
`update_material`. This service adds no operation, model-creation authority,
VMD editing, plugin loading, or unrestricted physics editing.

## Internal surface

`mmd_registry._internal` and its descendants are implementation details. They
must not be imported by external callers and carry no compatibility guarantee.
The namespace currently exports nothing. Existing modules are not moved into
it during this checkpoint because relocation would create avoidable import
breakage before service and CLI boundaries exist.

## Legacy compatibility surface

Existing documented or regression-tested import and process entry points
remain available while the architecture is introduced. In particular, this
includes direct PMX leaf-module imports, the legacy
`mmd_registry.capabilities.get_pmx_capability_manifest` helper,
`mmd_registry.reporting`, `mmd_registry.validator`, `mmd_registry.cli`, and the
`check_assets.py` launcher.

Compatibility does not promote those paths into new canonical public APIs.
Callers should prefer the public namespaces above when an equivalent export is
available. A legacy path may be deprecated only through a separately reviewed
compatibility decision; it must not disappear as an incidental refactor.

## Dependency direction

Public modules may depend on internal implementation. Internal modules must
not depend on CLI parsing or presentation. The CLI may consume public APIs and
compatibility adapters, but public imports must never load the CLI, print, or
terminate the process.

The existing `edit` command routes preview and apply execution through
`mmd_registry.services`. Argument parsing, exit-code mapping, and rendering
remain presentation responsibilities of the CLI.
