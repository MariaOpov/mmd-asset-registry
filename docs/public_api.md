# Public API policy

This document defines the package boundary introduced during the pre-0.9.0
architecture runway. It does not expand PMX editing authority or change any
v0.8.5 behavior.

## Public surface

Public names must be deliberately listed in the owning module's `__all__`.
They must be typed, deterministic, side-effect-controlled, independent from
`argparse.Namespace`, and usable without printing, exiting the process, or
assuming the repository root is the current directory.

The current public namespaces are:

- `mmd_registry`, whose only root export is `__version__`;
- `mmd_registry.pmx`, for the typed PMX document, reader, validation, writer,
  and round-trip surface listed in its `__all__`;
- `mmd_registry.pmx.editing`, for the bounded declarative editing surface
  listed in its `__all__`;
- `mmd_registry.services`, for typed CLI-independent document, validation,
  editing, and capability use cases listed in its `__all__`.

Future public entry points must be exposed through an intentional documented
namespace and an explicit `__all__`; importing a module from the package does
not by itself make that module public. The service namespace delegates to the
existing v0.8 safety pipeline and does not expand editing authority.

## Internal surface

`mmd_registry._internal` and its descendants are implementation details. They
must not be imported by external callers and carry no compatibility guarantee.
The namespace currently exports nothing. Existing modules are not moved into
it during this checkpoint because relocation would create avoidable import
breakage before service and CLI boundaries exist.

## Legacy compatibility surface

Existing documented or regression-tested import and process entry points
remain available while the architecture is introduced. In particular, this
includes direct PMX leaf-module imports, `mmd_registry.capabilities`,
`mmd_registry.reporting`, `mmd_registry.validator`, `mmd_registry.cli`, and
the `check_assets.py` launcher.

Compatibility does not promote those paths into new canonical public APIs.
Callers should prefer the public namespaces above when an equivalent export is
available. A legacy path may be deprecated only through a separately reviewed
compatibility decision; it must not disappear as an incidental refactor.

## Dependency direction

Public modules may depend on internal implementation. Internal modules must
not depend on CLI parsing or presentation. The CLI may consume public APIs and
compatibility adapters, but public imports must never load the CLI, print, or
terminate the process.
