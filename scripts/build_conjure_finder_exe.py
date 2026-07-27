"""Build a portable ``Conjure Finder.exe`` (no Python required on the target PC).

Usage (from repo root, with venv active or via venv python)::

    python scripts/build_conjure_finder_exe.py

Writes:
  - ``dist/Conjure Finder.exe`` (PyInstaller output)
  - ``releases/ConjureFinder-vX.Y.Z-windows.exe`` (+ ``.sha256``, ``version.json``)
  - ``../Conjure Finder.exe`` (convenience copy next to this repo)

Does not embed API keys — recipients use Settings… / ``conjure_finder.env`` beside the exe.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT.parent
EXE_NAME = "Conjure Finder"
DIST_EXE = ROOT / "dist" / f"{EXE_NAME}.exe"
FINAL_EXE = OUT_DIR / f"{EXE_NAME}.exe"
RELEASES_DIR = ROOT / "releases"

HIDDEN_IMPORTS = [
    "conjure_finder",
    "conjure_finder.__main__",
    "conjure_finder.bootstrap",
    "conjure_finder.gui",
    "conjure_finder.engine",
    "conjure_finder.batch",
    "conjure_finder.urls",
    "conjure_finder.settings",
    "conjure_finder.settings_ui",
    "conjure_finder.clipboard_bindings",
    "conjure_finder.updater",
    "bot",
    "bot.core",
    "bot.core.config",
    "bot.core.rate_limit",
    "bot.services",
    "bot.services.danbooru",
    "bot.services.rule34",
    "bot.services.conjure_pricing",
    "bot.utils",
    "bot.utils.booru_tags",
    "bot.utils.r34_tags",
    "bot.utils.artist_tags",
    "bot.utils.media_urls",
    "bot.utils.formatting",
    "bot.utils.currency",
    "bot.utils.media_policy",
    "dotenv",
    "httpx",
    "httpcore",
    "anyio",
    "certifi",
    "h11",
    "idna",
    "sniffio",
]


def _read_version() -> str:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "conjure_finder_version",
            ROOT / "conjure_finder" / "__init__.py",
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return str(getattr(mod, "__version__", "0.0.0"))
    except Exception:
        pass
    return "0.0.0"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            cwd=str(ROOT),
        )


def _run_regression_tests() -> None:
    """Abort the build if offline guarantee regressions fail."""
    tests = ROOT / "tests"
    if not tests.is_dir():
        raise SystemExit(f"ERROR: missing tests directory: {tests}")
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("Installing pytest (requirements-dev.txt)…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"],
            cwd=str(ROOT),
        )
    print("Running regression tests…", flush=True)
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(ROOT),
    )
    if rc != 0:
        raise SystemExit(
            f"ERROR: pytest failed (exit {rc}) — refusing to package exe."
        )
    print("Tests OK.", flush=True)


def _write_release_assets(src: Path, version: str) -> Path:
    """Copy space-free exe + checksum + version.json into ``releases/``."""
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    asset_name = f"ConjureFinder-v{version}-windows.exe"
    asset = RELEASES_DIR / asset_name
    shutil.copy2(src, asset)
    digest = _sha256(asset)
    (RELEASES_DIR / f"{asset_name}.sha256").write_text(
        f"{digest}  {asset_name}\n", encoding="utf-8"
    )
    # Space-free name expected by the optional auto-updater remote layout.
    remote_name = "ConjureFinder.exe"
    remote_copy = RELEASES_DIR / remote_name
    shutil.copy2(src, remote_copy)
    manifest = {
        "version": version,
        "filename": remote_name,
        "sha256": digest,
        "size": asset.stat().st_size,
        "url": "",
    }
    (RELEASES_DIR / "version.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return asset


def main() -> int:
    _run_regression_tests()
    _ensure_pyinstaller()

    entry = ROOT / "conjure_finder" / "__main__.py"
    work = ROOT / "build" / "pyinstaller"
    dist = ROOT / "dist"
    work.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        f"--name={EXE_NAME}",
        f"--distpath={dist}",
        f"--workpath={work}",
        f"--specpath={work}",
        f"--paths={ROOT}",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.append(f"--hidden-import={mod}")
    cmd.append(str(entry))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))

    if not DIST_EXE.is_file():
        print(f"ERROR: expected build output missing: {DIST_EXE}", file=sys.stderr)
        return 1

    version = _read_version()
    shutil.copy2(DIST_EXE, FINAL_EXE)
    asset = _write_release_assets(DIST_EXE, version)
    size_mb = asset.stat().st_size / (1024 * 1024)

    print(f"OK -> {FINAL_EXE} ({size_mb:.1f} MB)  version {version}")
    print(f"OK -> {asset}")
    print(
        "Share the releases/*.exe (or a GitHub Release). "
        "Recipients add keys via Settings... "
        "(creates conjure_finder.env beside it)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
