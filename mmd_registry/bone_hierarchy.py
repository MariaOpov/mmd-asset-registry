"""Safe parent-child hierarchy construction for presented PMX bones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence, TypeAlias

from mmd_registry.bone_explorer import BoneView


HierarchyIssueCode: TypeAlias = Literal[
    "duplicate_index",
    "invalid_parent",
    "cycle",
]


@dataclass(frozen=True, slots=True)
class BoneHierarchyIssue:
    """One non-fatal problem found while building a bone hierarchy."""

    code: HierarchyIssueCode
    bone_indices: tuple[int, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "code": self.code,
            "bone_indices": list(self.bone_indices),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class BoneHierarchyNode:
    """One flat hierarchy node and its direct children."""

    bone: BoneView
    child_indices: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "bone": self.bone.to_dict(),
            "child_indices": list(self.child_indices),
        }


@dataclass(frozen=True, slots=True)
class BoneHierarchy:
    """A safe, non-recursive representation of a bone hierarchy."""

    root_indices: tuple[int, ...]
    nodes: tuple[BoneHierarchyNode, ...]
    issues: tuple[BoneHierarchyIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "root_indices": list(self.root_indices),
            "node_count": len(self.nodes),
            "nodes": [node.to_dict() for node in self.nodes],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _canonicalize_cycle(
    cycle: tuple[int, ...],
) -> tuple[int, ...]:
    """Rotate a cycle so its smallest index appears first."""

    smallest_position = cycle.index(min(cycle))

    return cycle[smallest_position:] + cycle[:smallest_position]


def _find_parent_cycles(
    parent_by_index: dict[int, int | None],
) -> tuple[tuple[int, ...], ...]:
    """Find cycles where each node has at most one parent."""

    finished: set[int] = set()
    cycles: set[tuple[int, ...]] = set()

    for start_index in sorted(parent_by_index):
        if start_index in finished:
            continue

        path: list[int] = []
        path_positions: dict[int, int] = {}
        current_index: int | None = start_index

        while current_index is not None and current_index not in finished:
            if current_index in path_positions:
                cycle_start = path_positions[current_index]
                cycle = tuple(path[cycle_start:])
                cycles.add(_canonicalize_cycle(cycle))
                break

            path_positions[current_index] = len(path)
            path.append(current_index)
            current_index = parent_by_index[current_index]

        finished.update(path)

    return tuple(sorted(cycles))


def build_bone_hierarchy(
    views: Sequence[BoneView],
) -> BoneHierarchy:
    """Build safe relationships without modifying source views."""

    views_by_index: dict[int, BoneView] = {}
    duplicate_indices: set[int] = set()

    for view in views:
        if view.index in views_by_index:
            duplicate_indices.add(view.index)
            continue

        views_by_index[view.index] = view

    issues: list[BoneHierarchyIssue] = []

    for duplicate_index in sorted(duplicate_indices):
        issues.append(
            BoneHierarchyIssue(
                code="duplicate_index",
                bone_indices=(duplicate_index,),
                message=(
                    f"Duplicate bone index {duplicate_index}; "
                    "the first record was kept."
                ),
            )
        )

    parent_by_index: dict[int, int | None] = {}

    for bone_index in sorted(views_by_index):
        parent_index = views_by_index[bone_index].parent_index

        if parent_index == -1:
            parent_by_index[bone_index] = None
            continue

        if parent_index not in views_by_index:
            parent_by_index[bone_index] = None
            issues.append(
                BoneHierarchyIssue(
                    code="invalid_parent",
                    bone_indices=(bone_index,),
                    message=(
                        f"Bone {bone_index} references missing "
                        f"parent {parent_index}; "
                        "treated as a root."
                    ),
                )
            )
            continue

        parent_by_index[bone_index] = parent_index

    cycles = _find_parent_cycles(parent_by_index)
    cyclic_indices = {bone_index for cycle in cycles for bone_index in cycle}

    for cycle in cycles:
        cycle_text = ", ".join(str(bone_index) for bone_index in cycle)
        issues.append(
            BoneHierarchyIssue(
                code="cycle",
                bone_indices=cycle,
                message=(
                    f"Cycle detected among bones {cycle_text}; "
                    "cycle parent links were treated as roots."
                ),
            )
        )

    for bone_index in cyclic_indices:
        parent_by_index[bone_index] = None

    children_by_index: dict[int, list[int]] = {
        bone_index: [] for bone_index in views_by_index
    }
    root_indices: list[int] = []

    for bone_index in sorted(views_by_index):
        parent_index = parent_by_index[bone_index]

        if parent_index is None:
            root_indices.append(bone_index)
            continue

        children_by_index[parent_index].append(bone_index)

    nodes = tuple(
        BoneHierarchyNode(
            bone=views_by_index[bone_index],
            child_indices=tuple(children_by_index[bone_index]),
        )
        for bone_index in sorted(views_by_index)
    )

    return BoneHierarchy(
        root_indices=tuple(root_indices),
        nodes=nodes,
        issues=tuple(issues),
    )


def _tree_label(
    node: BoneHierarchyNode,
) -> str:
    """Return a safe one-line label for one hierarchy node."""

    display_name = " ".join(node.bone.display_name.split()) or "[unnamed]"

    return f"[{node.bone.index}] {display_name}"


def _format_tree_line(
    label: str,
    *,
    prefix: str,
    is_last: bool,
    is_root: bool,
) -> str:
    """Add the appropriate tree connector to one label."""

    if is_root:
        return label

    connector = "└── " if is_last else "├── "

    return f"{prefix}{connector}{label}"


def render_bone_tree(
    hierarchy: BoneHierarchy,
) -> str:
    """Render a hierarchy iteratively without recursion limits."""

    if not hierarchy.nodes:
        return "No bones found."

    nodes_by_index = {node.bone.index: node for node in hierarchy.nodes}
    lines: list[str] = []
    visited: set[int] = set()

    for root_index in hierarchy.root_indices:
        stack: list[tuple[int, str, bool, bool]] = [
            (
                root_index,
                "",
                True,
                True,
            )
        ]

        while stack:
            (
                bone_index,
                prefix,
                is_last,
                is_root,
            ) = stack.pop()

            node = nodes_by_index.get(bone_index)

            if node is None:
                missing_label = f"[{bone_index}] [missing]"
                lines.append(
                    _format_tree_line(
                        missing_label,
                        prefix=prefix,
                        is_last=is_last,
                        is_root=is_root,
                    )
                )
                continue

            label = _tree_label(node)

            if bone_index in visited:
                lines.append(
                    _format_tree_line(
                        f"{label} [already shown]",
                        prefix=prefix,
                        is_last=is_last,
                        is_root=is_root,
                    )
                )
                continue

            visited.add(bone_index)
            lines.append(
                _format_tree_line(
                    label,
                    prefix=prefix,
                    is_last=is_last,
                    is_root=is_root,
                )
            )

            child_prefix = "" if is_root else prefix + ("    " if is_last else "│   ")

            child_count = len(node.child_indices)

            for child_position in range(
                child_count - 1,
                -1,
                -1,
            ):
                child_index = node.child_indices[child_position]
                child_is_last = child_position == child_count - 1

                stack.append(
                    (
                        child_index,
                        child_prefix,
                        child_is_last,
                        False,
                    )
                )

    return "\n".join(lines)
