"""Version compare + update script helpers for Conjure Finder auto-update."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from conjure_finder.updater import (
    EXE_NAME,
    PROTECTED_SIDECARS,
    UPDATE_PS1,
    build_update_bat,
    build_update_ps1,
    is_newer,
    parse_version,
)


class VersionCompareTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("v1.0"), (1, 0, 0))

    def test_newer(self) -> None:
        self.assertTrue(is_newer("1.0.1", "1.0.0"))
        self.assertTrue(is_newer("1.1.0", "1.0.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))

    def test_update_ps1_swaps_without_relaunch(self) -> None:
        text = build_update_ps1(
            pid=4242,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        self.assertIn("$pidToWait = 4242", text)
        self.assertIn("Copy-Item -LiteralPath $new -Destination $target", text)
        self.assertIn("explorer.exe", text)
        self.assertIn("_UPDATE_START_HERE.txt", text)
        self.assertIn("Conjure Finder.exe", text)
        self.assertNotIn("Start-Process -FilePath $target", text)
        self.assertNotIn("$pid =", text)

    def test_update_ps1_refuses_wrong_target_basename(self) -> None:
        text = build_update_ps1(
            pid=1,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        self.assertIn("refusing_update_wrong_target", text)
        self.assertIn("refusing_update_wrong_new", text)
        self.assertIn("$expectedLeaf", text)

    def test_update_ps1_does_not_touch_sibling_tools_or_user_data(self) -> None:
        """Co-located Sparse Tag Browser + conjure_finder.env must survive updates."""
        text = build_update_ps1(
            pid=1,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        for name in PROTECTED_SIDECARS:
            self.assertIn(name, text)
        self.assertNotIn("Get-ChildItem", text)
        self.assertNotIn("Remove-Item -Recurse", text)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("Remove-Item"):
                continue
            self.assertTrue(
                any(tok in stripped for tok in ("$bak", "$new", "$log", "$PSCommandPath")),
                msg=f"unexpected Remove-Item: {stripped}",
            )
            # Never remove a protected sidecar by literal name.
            for name in PROTECTED_SIDECARS:
                self.assertNotIn(name, stripped)

    def test_protected_sidecars_cover_sparse_tag_browser(self) -> None:
        self.assertIn("Sparse Tag Browser.exe", PROTECTED_SIDECARS)
        self.assertIn("conjure_finder.env", PROTECTED_SIDECARS)
        self.assertIn("sparse_tags_favourites.json", PROTECTED_SIDECARS)
        self.assertIn("sparse_tags_prefs.json", PROTECTED_SIDECARS)

    def test_update_download_name_is_only_conjure_exe_new(self) -> None:
        self.assertEqual(EXE_NAME, "Conjure Finder.exe")
        self.assertEqual(f"{EXE_NAME}.new", "Conjure Finder.exe.new")

    def test_simulated_folder_sidecars_untouched_by_script_ops(self) -> None:
        """Sanity: script text never names Remove-Item on sidecar paths in a real folder layout."""
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / EXE_NAME).write_bytes(b"old")
            (folder / f"{EXE_NAME}.new").write_bytes(b"new")
            for name in PROTECTED_SIDECARS:
                (folder / name).write_text("keep", encoding="utf-8")
            text = build_update_ps1(
                pid=1,
                current=folder / EXE_NAME,
                new_exe=folder / f"{EXE_NAME}.new",
            )
            for name in PROTECTED_SIDECARS:
                # May appear in the protected-list comment only.
                for line in text.splitlines():
                    if "Remove-Item" in line and name in line:
                        self.fail(f"Remove-Item targets protected sidecar {name}: {line}")
            # Files still on disk (script was not executed — just ensure we created them).
            for name in PROTECTED_SIDECARS:
                self.assertTrue((folder / name).is_file())

    def test_update_bat_launches_powershell(self) -> None:
        text = build_update_bat(
            pid=4242,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        self.assertIn("powershell.exe", text)
        self.assertIn(UPDATE_PS1, text)


if __name__ == "__main__":
    unittest.main()
