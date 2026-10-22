"""v0.9.5.11 private Smart Morph first-slice inspection (read-only).

No morph mutation, save, writer, weight, preview, plan, CLI or apply path.
"""

from __future__ import annotations

import hashlib
import io

from mmd_registry._smart_morph_readonly import (
    SmartMorphCapability,
    SmartMorphCapabilityStatus,
    SmartMorphIdentity,
    SmartMorphInspection,
    _canonical_candidate_traces,
    _project_traces,
)
from mmd_registry.pmx import load_pmx
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services.structural_authoring_catalog import (
    PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT,
    PmxStructuralAuthoringMorphCatalogEntry,
    inspect_structural_authoring_catalog,
)
from mmd_registry.smart_part_detection import _match_smart_part_candidate_traces
from mmd_registry.smart_parts import SmartPartEvidenceKind, SmartPartKind


# Frozen slot-specific exact alias filters, applied ONLY to detector matches.
# They are not a second matcher and do not classify raw PMX name strings.
_SLOTS: tuple[tuple[str, SmartPartKind, frozenset[str]], ...] = (
    ("smile", SmartPartKind.FACE, frozenset(("smile", "笑顔", "笑い"))),
    ("blink", SmartPartKind.EYES, frozenset(("blink", "まばたき"))),
)


def _collect_morph_catalog(document: object) -> tuple[PmxStructuralAuthoringMorphCatalogEntry, ...]:
    """Use the existing paginated catalog service; never synthesize a reader."""
    entries: list[PmxStructuralAuthoringMorphCatalogEntry] = []
    offset = 0
    while True:
        page = inspect_structural_authoring_catalog(
            document,  # type: ignore[arg-type]
            PmxReferenceTargetKind.MORPH,
            offset=offset,
            limit=PMX_STRUCTURAL_AUTHORING_CATALOG_MAX_LIMIT,
        )
        entries.extend(page.entries)
        following = offset + page.returned_count
        if following >= page.total_count:
            break
        if page.returned_count == 0:
            # Fail closed in _catalog_matches_document; no partial evidence support.
            break
        offset = following
    return tuple(entries)


def _catalog_matches_document(
    entries: tuple[PmxStructuralAuthoringMorphCatalogEntry, ...],
    morphs: tuple[SmartMorphIdentity, ...],
) -> bool:
    """Ensure catalog identity is exactly one same-source document projection."""
    if len(entries) != len(morphs):
        return False
    matched: set[int] = set()
    for entry in entries:
        if not isinstance(entry, PmxStructuralAuthoringMorphCatalogEntry):
            return False
        index = entry.source_index
        if type(index) is not int or index in matched or not 0 <= index < len(morphs):
            return False
        matched.add(index)
        morph = morphs[index]
        if (
            entry.local_name != morph.local_name
            or entry.universal_name != morph.universal_name
            or entry.panel_name != morph.panel_name
            or entry.morph_type_name != morph.morph_type_name
            or entry.offset_count != morph.offset_count
        ):
            return False
    return len(matched) == len(morphs)


def _resolve_slot(
    kind: str,
    part_kind: SmartPartKind,
    aliases: frozenset[str],
    all_traces: tuple[object, ...],
    morphs: tuple[SmartMorphIdentity, ...],
    source_mismatch: bool,
) -> SmartMorphCapability:
    # Full pre-filter traces retain conflicting recognized local/universal names.
    direct_traces = tuple(
        trace for trace in all_traces
        if trace.evidence.source_kind is SmartPartEvidenceKind.MORPH  # type: ignore[attr-defined]
    )
    slot_traces = tuple(
        trace for trace in direct_traces
        if trace.kind is part_kind and trace.matched_alias in aliases  # type: ignore[attr-defined]
    )
    indices = tuple(sorted({trace.evidence.source_index for trace in slot_traces}))
    source_groups: dict[int, tuple[object, ...]] = {}
    for idx in indices:
        source_groups[idx] = tuple(
            trace for trace in direct_traces if trace.evidence.source_index == idx  # type: ignore[attr-defined]
        )
    conflicting = tuple(
        idx for idx in indices
        if len({trace.kind for trace in source_groups[idx]}) > 1  # type: ignore[attr-defined]
    )
    if conflicting:
        # Include all recognized counterpart traces on conflicted indices.
        conflict_traces = tuple(
            trace for idx in conflicting for trace in source_groups[idx]
        )
        evidence_traces = tuple(slot_traces) + conflict_traces
    else:
        evidence_traces = slot_traces
    explanations = _project_traces(_canonical_candidate_traces(evidence_traces))  # type: ignore[arg-type]

    if source_mismatch:
        reason = "source_evidence_mismatch"
    elif conflicting:
        reason = "same_source_exact_conflict"
    elif len(indices) > 1:
        reason = "multiple_exact_morph_candidates"
    elif not indices:
        reason = "no_exact_morph_evidence"
    elif indices[0] >= len(morphs):
        reason = "source_evidence_mismatch"
    elif morphs[indices[0]].morph_type not in (1, 2):
        reason = "morph_type_out_of_scope"
    elif morphs[indices[0]].offset_count == 0:
        reason = "empty_morph_offsets"
    else:
        reason = "exact_morph_evidence"

    statuses = {
        "source_evidence_mismatch": SmartMorphCapabilityStatus.BLOCKED,
        "same_source_exact_conflict": SmartMorphCapabilityStatus.BLOCKED,
        "multiple_exact_morph_candidates": SmartMorphCapabilityStatus.BLOCKED,
        "no_exact_morph_evidence": SmartMorphCapabilityStatus.UNSUPPORTED,
        "morph_type_out_of_scope": SmartMorphCapabilityStatus.UNSUPPORTED,
        "empty_morph_offsets": SmartMorphCapabilityStatus.UNSUPPORTED,
        "exact_morph_evidence": SmartMorphCapabilityStatus.SUPPORTED,
    }
    return SmartMorphCapability(
        part_kind=part_kind,
        capability_kind=kind,
        status=statuses[reason],
        reason=reason,
        candidate_indices=indices,
        evidence=explanations,
    )


def inspect_smart_morphs(source_bytes: bytes) -> SmartMorphInspection:
    """Describe only model-local morph inventory and exact smile/blink evidence.

    ``source_bytes`` is an exact binary PMX. Private source identities and model
    names are returned in-memory but NEVER printed, written or logged here.
    """
    if type(source_bytes) is not bytes:
        raise TypeError("source_bytes must be bytes, not a path or file handle.")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    document = load_pmx(io.BytesIO(source_bytes))  # sole existing parser; once
    morphs = tuple(
        SmartMorphIdentity(
            source_index=index,
            local_name=morph.local_name,
            universal_name=morph.universal_name,
            panel=morph.panel,
            panel_name=morph.panel_name,
            morph_type=morph.morph_type,
            morph_type_name=morph.morph_type_name,
            offset_count=len(morph.offsets),
        )
        for index, morph in enumerate(document.morphs)
    )
    entries = _collect_morph_catalog(document)
    mismatch = not _catalog_matches_document(entries, morphs)
    # If a tampered/malformed catalog contains foreign DTO types, fail closed
    # via the source-mismatch status rather than calling detector on bad entries.
    detector_entries = tuple(e for e in entries if isinstance(e, PmxStructuralAuthoringMorphCatalogEntry))
    traces = _canonical_candidate_traces(
        tuple(
            t for t in _match_smart_part_candidate_traces(detector_entries)
            if t.evidence.source_kind is SmartPartEvidenceKind.MORPH
        )
    )
    capabilities = tuple(
        _resolve_slot(slot, kind, aliases, traces, morphs, mismatch)
        for slot, kind, aliases in _SLOTS
    )
    return SmartMorphInspection(
        source_sha256=source_sha256,
        morphs=morphs,
        capabilities=capabilities,
    )
