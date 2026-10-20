"""Create a Desktop shortcut to TL Resonance Calc.vbs."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def _vbs_str(path: Path) -> str:
    """Escape a filesystem path for a VBScript string literal."""
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '" & Chr(34) & "')


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "TL Resonance Calc.vbs"
    if not target.exists():
        print(f"Missing launcher: {target}", file=sys.stderr)
        return 1

    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.is_dir():
        print(f"Desktop folder not found under {Path.home()}", file=sys.stderr)
        return 1

    shortcut = desktop / "TL Resonance Calc.lnk"
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'Set sc = sh.CreateShortcut("{_vbs_str(shortcut)}")\r\n'
        f'sc.TargetPath = "{_vbs_str(target)}"\r\n'
        f'sc.WorkingDirectory = "{_vbs_str(root)}"\r\n'
        'sc.Description = "Torchlight Infinite resonance FE/hour calculator"\r\n'
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
    print(f"Points to:\n  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
