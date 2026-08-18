"""v0.9.1 destination-path and publication-race safety regression gates."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
from mmd_registry.pmx.collection_transform import PmxStructuralTransformIntent
from mmd_registry.pmx.editing import (
    PmxEditPathError,
    parse_pmx_edit_plan_json,
    write_pmx_edit,
)
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.structural_output import (
    PmxStructuralOutputPathError,
    write_pmx_structural_transform,
)
from mmd_registry.pmx.writer import serialize_pmx
from tests.mmd_fixtures import build_pmx_bone, build_pmx_structure
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


def _clean_structural_source_bytes() -> bytes:
    document = replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )
    return serialize_pmx(document)


class V091DestinationSafetyTests(unittest.TestCase):
    """Harden the shared v0.8/v0.9.1 destination-safety boundary."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        self.edit_source = self.root / "edit-source.pmx"
        self.edit_source_bytes = build_pmx_structure(
            bones=(build_pmx_bone(),),
        )
        self.edit_source.write_bytes(self.edit_source_bytes)
        self.edit_plan = parse_pmx_edit_plan_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {
                            "op": "set_model_info",
                            "local_name": "CP04 destination safety",
                        }
                    ],
                }
            )
        )

        self.structural_source = self.root / "structural-source.pmx"
        self.structural_source_bytes = _clean_structural_source_bytes()
        self.structural_source.write_bytes(self.structural_source_bytes)
        self.structural_intent = PmxStructuralTransformIntent()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _temporary_outputs(destination: Path) -> list[Path]:
        return list(
            destination.parent.glob(f".{destination.name}.*.tmp")
        )

    def _publish_collision(self, destination: Path, racer_bytes: bytes):
        expected = destination.resolve(strict=False)

        def collide(source, target, *args, **kwargs) -> None:
            del args, kwargs
            temporary = Path(source)
            publish_target = Path(target)
            self.assertEqual(
                publish_target.resolve(strict=False),
                expected,
            )
            self.assertTrue(temporary.is_file())
            self.assertFalse(publish_target.exists())
            publish_target.write_bytes(racer_bytes)
            raise FileExistsError("simulated CP04 publish collision")

        return collide

    def test_edit_dotdot_alias_to_source_is_refused(self) -> None:
        nested = self.root / "nested-edit"
        nested.mkdir()
        alias = nested / ".." / self.edit_source.name

        with self.assertRaisesRegex(PmxEditPathError, "different files"):
            write_pmx_edit(
                self.edit_source,
                alias,
                self.edit_plan,
                overwrite=True,
            )

        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)

    def test_structural_dotdot_alias_to_source_is_refused(self) -> None:
        nested = self.root / "nested-structural"
        nested.mkdir()
        alias = nested / ".." / self.structural_source.name

        with self.assertRaisesRegex(
            PmxStructuralOutputPathError,
            "different files",
        ):
            write_pmx_structural_transform(
                self.structural_source,
                alias,
                self.structural_intent,
                overwrite=True,
            )

        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )

    @unittest.skipUnless(os.name == "nt", "Windows path semantics only")
    def test_windows_case_only_aliases_are_refused(self) -> None:
        edit_alias = self.edit_source.with_name("EDIT-SOURCE.PMX")
        with self.assertRaises(PmxEditPathError):
            write_pmx_edit(
                self.edit_source,
                edit_alias,
                self.edit_plan,
                overwrite=True,
            )

        structural_alias = self.structural_source.with_name(
            "STRUCTURAL-SOURCE.PMX"
        )
        with self.assertRaises(PmxStructuralOutputPathError):
            write_pmx_structural_transform(
                self.structural_source,
                structural_alias,
                self.structural_intent,
                overwrite=True,
            )

        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)
        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )

    def test_edit_hardlink_source_alias_cannot_be_output_target(self) -> None:
        source_alias = self.root / "edit-source-hardlink.pmx"
        try:
            os.link(self.edit_source, source_alias)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")

        with self.assertRaisesRegex(PmxEditPathError, "same file"):
            write_pmx_edit(
                source_alias,
                self.edit_source,
                self.edit_plan,
                overwrite=True,
            )

        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)

    def test_structural_hardlink_source_alias_cannot_be_output_target(self) -> None:
        source_alias = self.root / "structural-source-hardlink.pmx"
        try:
            os.link(self.structural_source, source_alias)
        except OSError as error:
            self.skipTest(f"hardlinks unavailable: {error}")

        with self.assertRaisesRegex(
            PmxStructuralOutputPathError,
            "same file",
        ):
            write_pmx_structural_transform(
                source_alias,
                self.structural_source,
                self.structural_intent,
                overwrite=True,
            )

        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )

    def test_edit_no_clobber_publish_collision_preserves_racer(self) -> None:
        destination = self.root / "edit-race.pmx"
        racer = b"CP04 edit racer"

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=self._publish_collision(destination, racer),
        ):
            with self.assertRaisesRegex(PmxEditPathError, "already exists"):
                write_pmx_edit(
                    self.edit_source,
                    destination,
                    self.edit_plan,
                )

        self.assertEqual(destination.read_bytes(), racer)
        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_structural_no_clobber_publish_collision_preserves_racer(
        self,
    ) -> None:
        destination = self.root / "structural-race.pmx"
        racer = b"CP04 structural racer"

        with patch(
            "mmd_registry.pmx.editing.output.os.link",
            side_effect=self._publish_collision(destination, racer),
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "already exists",
            ):
                write_pmx_structural_transform(
                    self.structural_source,
                    destination,
                    self.structural_intent,
                )

        self.assertEqual(destination.read_bytes(), racer)
        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_edit_second_destination_check_rejects_hardlink_race(self) -> None:
        destination = self.root / "edit-hardlink-race.pmx"
        original = edit_output._validate_destination_state
        calls = 0

        def race(source: Path, output: Path, *, overwrite: bool) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                os.link(source, output)
            original(source, output, overwrite=overwrite)

        with patch(
            "mmd_registry.pmx.editing.output._validate_destination_state",
            side_effect=race,
        ):
            with self.assertRaisesRegex(PmxEditPathError, "same file"):
                write_pmx_edit(
                    self.edit_source,
                    destination,
                    self.edit_plan,
                    overwrite=True,
                )

        self.assertEqual(calls, 2)
        self.assertTrue(self.edit_source.samefile(destination))
        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_structural_second_destination_check_rejects_hardlink_race(
        self,
    ) -> None:
        destination = self.root / "structural-hardlink-race.pmx"
        original = edit_output._validate_destination_state
        calls = 0

        def race(source: Path, output: Path, *, overwrite: bool) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                os.link(source, output)
            original(source, output, overwrite=overwrite)

        with patch(
            "mmd_registry.pmx.editing.output._validate_destination_state",
            side_effect=race,
        ):
            with self.assertRaisesRegex(
                PmxStructuralOutputPathError,
                "same file",
            ):
                write_pmx_structural_transform(
                    self.structural_source,
                    destination,
                    self.structural_intent,
                    overwrite=True,
                )

        self.assertEqual(calls, 2)
        self.assertTrue(self.structural_source.samefile(destination))
        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )
        self.assertEqual(self._temporary_outputs(destination), [])

    def test_edit_source_symlink_to_output_target_is_refused(self) -> None:
        source_link = self.root / "edit-source-link.pmx"
        try:
            source_link.symlink_to(self.edit_source)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaises(PmxEditPathError):
            write_pmx_edit(
                source_link,
                self.edit_source,
                self.edit_plan,
                overwrite=True,
            )

        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)

    def test_structural_source_symlink_to_output_target_is_refused(
        self,
    ) -> None:
        source_link = self.root / "structural-source-link.pmx"
        try:
            source_link.symlink_to(self.structural_source)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaises(PmxStructuralOutputPathError):
            write_pmx_structural_transform(
                source_link,
                self.structural_source,
                self.structural_intent,
                overwrite=True,
            )

        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )

    def test_parent_symlink_retarget_does_not_redirect_edit_output(self) -> None:
        first_parent = self.root / "first-parent"
        second_parent = self.root / "second-parent"
        parent_link = self.root / "parent-link"
        first_parent.mkdir()
        second_parent.mkdir()

        try:
            parent_link.symlink_to(first_parent, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks unavailable: {error}")

        requested_output = parent_link / "output.pmx"
        resolved_output = first_parent / "output.pmx"
        redirected_output = second_parent / "output.pmx"
        original_serialize = edit_output.serialize_pmx

        def serialize_then_retarget(document) -> bytes:
            data = original_serialize(document)
            parent_link.unlink()
            parent_link.symlink_to(second_parent, target_is_directory=True)
            return data

        with patch(
            "mmd_registry.pmx.editing.output.serialize_pmx",
            side_effect=serialize_then_retarget,
        ):
            write_pmx_edit(
                self.edit_source,
                requested_output,
                self.edit_plan,
            )

        self.assertTrue(resolved_output.is_file())
        self.assertFalse(redirected_output.exists())
        self.assertEqual(self.edit_source.read_bytes(), self.edit_source_bytes)

    def test_structural_writer_reuses_shared_destination_safety_hooks(
        self,
    ) -> None:
        destination = self.root / "shared-kernel.pmx"
        original_resolve = edit_output._resolve_edit_paths
        original_commit = edit_output._commit_verified_bytes

        with patch(
            "mmd_registry.pmx.editing.output._resolve_edit_paths",
            wraps=original_resolve,
        ) as resolve_paths:
            with patch(
                "mmd_registry.pmx.editing.output._commit_verified_bytes",
                wraps=original_commit,
            ) as commit_bytes:
                write_pmx_structural_transform(
                    self.structural_source,
                    destination,
                    self.structural_intent,
                )

        resolve_paths.assert_called_once()
        commit_bytes.assert_called_once()
        self.assertTrue(destination.is_file())
        self.assertEqual(
            self.structural_source.read_bytes(),
            self.structural_source_bytes,
        )


if __name__ == "__main__":
    unittest.main()
