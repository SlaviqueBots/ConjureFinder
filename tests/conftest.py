"""Offline test bootstrap — no live Danbooru / Rule34."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# bot.core.config.Config.load() runs at import and requires BOT_TOKEN.
os.environ.setdefault("BOT_TOKEN", "conjure-finder-test-unused")
