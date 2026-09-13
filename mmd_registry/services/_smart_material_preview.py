"""Private Smart Material draft-to-preview bridge for v0.9.5.7."""

from __future__ import annotations

from mmd_registry.pmx.editing.plan import PmxEditPlan
from mmd_registry.pmx.editing.preview import PmxEditPreview
from mmd_registry.services import preview_edit


def preview_smart_material_color_draft(
    source_bytes: bytes,
    draft: PmxEditPlan,
) -> PmxEditPreview:
    """Preview one certified Smart Material draft through existing authority."""

    return preview_edit(source_bytes, draft)
