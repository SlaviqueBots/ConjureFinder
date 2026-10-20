"""Build a portable ``Sparse Tag Browser.exe`` (no Python on the target PC).

Usage (from repo root)::

    python scripts/build_sparse_tag_browser_exe.py

Writes:
  - ``dist/Sparse Tag Browser.exe``
  - ``releases/SparseTagBrowser-vX.Y.Z-windows.exe`` (+ ``.sha256``)
  - ``releases/sparse_tags/version.json`` + ``SparseTagBrowser.exe`` (update server payload)
  - ``../Sparse Tag Browser.exe`` (convenience copy next to this repo)

Does not embed API keys — uses ``conjure_finder.env`` beside the exe (same as Conjure Finder).
User data: ``sparse_tags_prefs.json``, ``sparse_tags_favourites.json``,
``sparse_tags_seen.json``, ``sparse_tags_combo.json`` beside the exe.
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
EXE_NAME = "Sparse Tag Browser"
DIST_EXE = ROOT / "dist" / f"{EXE_NAME}.exe"
FINAL_EXE = OUT_DIR / f"{EXE_NAME}.exe"
RELEASES_DIR = ROOT / "releases"
UPDATE_PAYLOAD_DIR = RELEASES_DIR / "sparse_tags"

HIDDEN_IMPORTS = [
    "sparse_tags",
    "sparse_tags.__main__",
    "sparse_tags.bootstrap",
    "sparse_tags.gui",
    "sparse_tags.fetch",
    "sparse_tags.favourites",
    "sparse_tags.history",
    "sparse_tags.prefs",
    "sparse_tags.combo",
    "sparse_tags.combo_ui",
    "sparse_tags.theme",
    "sparse_tags.updater",
    "bot",
    "bot.core",
    "bot.core.config",
    "bot.core.rate_limit",
    "bot.services",
    "bot.services.danbooru",
    "bot.services.rule34",
    "bot.utils",
    "bot.utils.booru_tags",
    "bot.utils.r34_tags",
    "bot.utils.media_urls",
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
            "sparse_tags_version",
            ROOT / "sparse_tags" / "__init__.py",
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


def _run_updater_tests() -> None:
    print("Running Sparse Tag Browser updater tests…", flush=True)
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "tests/test_sparse_tags_updater.py", "tests/test_sparse_tags_combo.py", "-q"],
        cwd=str(ROOT),
    )
    if rc != 0:
        raise SystemExit(f"ERROR: pytest failed (exit {rc}) — refusing to package exe.")
    print("Tests OK.", flush=True)


def _write_release_assets(src: Path, version: str) -> Path:
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)

    asset_name = f"SparseTagBrowser-v{version}-windows.exe"
    asset = RELEASES_DIR / asset_name
    shutil.copy2(src, asset)
    digest = _sha256(asset)
    (RELEASES_DIR / f"{asset_name}.sha256").write_text(
        f"{digest}  {asset_name}\n", encoding="utf-8"
    )

    remote_name = "SparseTagBrowser.exe"
    remote_copy = UPDATE_PAYLOAD_DIR / remote_name
    shutil.copy2(src, remote_copy)
    # Also keep a copy under releases/ for easy grabbing.
    shutil.copy2(src, RELEASES_DIR / remote_name)

    manifest = {
        "version": version,
        "filename": remote_name,
        "sha256": digest,
        "size": asset.stat().st_size,
        "url": "",
    }
    (UPDATE_PAYLOAD_DIR / "version.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return asset


def main() -> int:
    _run_updater_tests()
    _ensure_pyinstaller()

    entry = ROOT / "sparse_tags" / "__main__.py"
    work = ROOT / "build" / "pyinstaller_sparse_tags"
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
    print(f"OK -> {UPDATE_PAYLOAD_DIR / 'version.json'} (serve this folder on update port 8768)")
    print(
        "Ship the releases/*.exe. Recipients put it next to Conjure Finder.exe "
        "and conjure_finder.env — no keys inside the binary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
