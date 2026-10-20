"""Create a Desktop shortcut to Sparse Tag Browser.vbs (dev code + portable data)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def _vbs_str(path: Path) -> str:
    """Escape a filesystem path for a VBScript string literal."""
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '" & Chr(34) & "')


def _default_portable_dir() -> Path | None:
    home = Path.home()
    for base in (
        home / "Desktop" / "Conjure Finder",
        home / "OneDrive" / "Desktop" / "Conjure Finder",
    ):
        if (base / "Sparse Tag Browser.exe").is_file() or (
            base / "sparse_tags_prefs.json"
        ).is_file():
            return base.resolve()
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "Sparse Tag Browser.vbs"
    if not target.exists():
        print(f"Missing launcher: {target}", file=sys.stderr)
        return 1

    portable = _default_portable_dir()
    tip = root / "sparse_tags_data_root.txt"
    if portable is not None:
        tip.write_text(str(portable) + "\n", encoding="utf-8")

    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.is_dir():
        print(f"Desktop folder not found under {Path.home()}", file=sys.stderr)
        return 1

    shortcut = desktop / "Sparse Tag Browser.lnk"
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'Set sc = sh.CreateShortcut("{_vbs_str(shortcut)}")\r\n'
        f'sc.TargetPath = "{_vbs_str(target)}"\r\n'
        f'sc.WorkingDirectory = "{_vbs_str(root)}"\r\n'
        'sc.Description = "Sparse Tag Browser (dev code, portable settings)"\r\n'
        "sc.WindowStyle = 1\r\n"
        "sc.Save\r\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".vbs", delete=False, encoding="utf-8", newline="\r\n"
    ) as f:
        f.write(vbs)
        tmp = f.name
    try:
        subprocess.run(["cscript", "//nologo", tmp], check=True)
    finally:
        Path(tmp).unlink(missing_ok=True)

    print(f"Desktop shortcut created:\n  {shortcut}")
    print(f"Points to (dev code):\n  {target}")
    if portable is not None:
        print(f"Settings / history / keys folder:\n  {portable}")
    else:
        print(
            "No portable Conjure Finder folder found on Desktop — "
            "dev will use the repo folder for settings."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
