"""Load env before any bot imports (CFG reads env at import time)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = _app_root()


def ensure_path() -> None:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and meipass not in sys.path:
            sys.path.insert(0, str(meipass))
        return
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def load_env() -> None:
    """Load optional key files. Later files win.

    Order:
      1. project ``.env`` (optional)
      2. ``conjure_finder.env`` — preferred; also written by Settings…
    """
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    pc = ROOT / "conjure_finder.env"
    if pc.exists():
        load_dotenv(pc, override=True)
    # BOT_TOKEN is required by Config.load(); finder never talks to Telegram.
    os.environ.setdefault("BOT_TOKEN", os.environ.get("BOT_TOKEN") or "conjure-finder-unused")


def apply_env() -> None:
    """Ensure import path + env files (handy for one-off scripts)."""
    ensure_path()
    load_env()
