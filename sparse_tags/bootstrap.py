"""Load env before any bot/config imports (CFG reads env at import time)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Source tree (ConjureFinder repo) — used for imports in dev."""
    return Path(__file__).resolve().parents[1]


def _env_data_root() -> Path | None:
    raw = (os.environ.get("SPARSE_TAGS_ROOT") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_dir() else None


def _tip_data_root(repo: Path) -> Path | None:
    """Optional one-line path in ``sparse_tags_data_root.txt`` (gitignored)."""
    tip = repo / "sparse_tags_data_root.txt"
    if not tip.is_file():
        return None
    try:
        line = tip.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except OSError:
        return None
    if not line:
        return None
    path = Path(line).expanduser()
    return path.resolve() if path.is_dir() else None


def _portable_candidates(repo: Path) -> list[Path]:
    home = Path.home()
    out: list[Path] = []
    for base in (
        home / "Desktop" / "Conjure Finder",
        home / "OneDrive" / "Desktop" / "Conjure Finder",
        repo.parent,
        repo,
    ):
        try:
            resolved = base.resolve()
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        if (resolved / "Sparse Tag Browser.exe").is_file() or (
            resolved / "sparse_tags_prefs.json"
        ).is_file():
            if resolved not in out:
                out.append(resolved)
    return out


def _score_data_root(path: Path) -> tuple[float, int, int]:
    """Prefer the install with the newest user JSON (and an exe if tied)."""
    newest = 0.0
    files = 0
    for name in (
        "sparse_tags_prefs.json",
        "sparse_tags_seen.json",
        "sparse_tags_favourites.json",
        "sparse_tags_combo.json",
    ):
        f = path / name
        if not f.is_file():
            continue
        files += 1
        try:
            newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    has_exe = 1 if (path / "Sparse Tag Browser.exe").is_file() else 0
    return (newest, files, has_exe)


def _find_data_root() -> Path:
    """Folder for prefs / favourites / seen / keys (same as the portable exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    env = _env_data_root()
    if env is not None:
        return env

    repo = _repo_root()
    tip = _tip_data_root(repo)
    if tip is not None:
        return tip

    candidates = _portable_candidates(repo)
    if candidates:
        return max(candidates, key=_score_data_root)
    return repo


ROOT = _find_data_root()

# Set by load_env() — which conjure_finder.env (if any) was applied.
LOADED_KEYS_PATH: Path | None = None


def set_app_root(path: Path | str) -> None:
    """Point user-data paths at a folder (tests / special launchers)."""
    global ROOT
    ROOT = Path(path).resolve()
    mapping = {
        "sparse_tags.prefs": ("PREFS_PATH", "sparse_tags_prefs.json"),
        "sparse_tags.favourites": ("FAVOURITES_PATH", "sparse_tags_favourites.json"),
        "sparse_tags.history": ("SEEN_PATH", "sparse_tags_seen.json"),
        "sparse_tags.combo": ("COMBO_PATH", "sparse_tags_combo.json"),
    }
    for mod_name, (attr, filename) in mapping.items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            setattr(mod, attr, ROOT / filename)


def ensure_path() -> None:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in sys.path:
            sys.path.insert(0, str(meipass))
        return
    # Dev: import the package from the repo even when ROOT is the portable folder.
    repo = str(_repo_root())
    if repo not in sys.path:
        sys.path.insert(0, repo)


def load_env() -> None:
    """Load keys from the portable install folder (same as Conjure Finder / exe).

    Order (later wins):
      1. repo ``.env`` (optional, dev)
      2. ``conjure_finder.env`` in ROOT (portable / exe folder)
      3. repo ``conjure_finder.env`` fallback if ROOT has none
    """
    global LOADED_KEYS_PATH
    from dotenv import load_dotenv

    repo = _repo_root()
    load_dotenv(repo / ".env")
    LOADED_KEYS_PATH = None
    for candidate in (ROOT / "conjure_finder.env", repo / "conjure_finder.env"):
        if candidate.is_file():
            load_dotenv(candidate, override=True)
            LOADED_KEYS_PATH = candidate
            break
    os.environ.setdefault(
        "BOT_TOKEN", os.environ.get("BOT_TOKEN") or "sparse-tags-unused"
    )


def apply_env() -> None:
    ensure_path()
    load_env()
