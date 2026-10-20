"""Persistent recorded tags + pair-search URL builders (Danbooru / Rule34)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import quote

from sparse_tags.bootstrap import ROOT

COMBO_PATH = ROOT / "sparse_tags_combo.json"

DANBOORU_BASE = "https://danbooru.donmai.us"
R34_SITE = "https://rule34.xxx"

Mode = Literal["danbooru", "rule34"]
Rating = Literal["", "g", "s", "q", "e"]

DEFAULT_R34_NEGATIVES = ["furry", "anthro", "guro"]


def _empty_pool() -> dict[str, list[str]]:
    return {"recorded": [], "enabled": []}


def _empty_pools() -> dict[str, dict[str, list[str]]]:
    return {"danbooru": _empty_pool(), "rule34": _empty_pool()}


@dataclass
class ComboState:
    """Site mode + per-site recorded partner pools (Danbooru ≠ Rule34 tags)."""

    mode: Mode = "danbooru"
    rating: Rating = ""
    r34_negatives: list[str] = field(
        default_factory=lambda: list(DEFAULT_R34_NEGATIVES)
    )
    pools: dict[str, dict[str, list[str]]] = field(default_factory=_empty_pools)

    def _pool(self, mode: Mode | None = None) -> dict[str, list[str]]:
        key = mode or self.mode
        if key not in self.pools:
            self.pools[key] = _empty_pool()
        pool = self.pools[key]
        pool.setdefault("recorded", [])
        pool.setdefault("enabled", [])
        return pool

    @property
    def recorded(self) -> list[str]:
        return self._pool()["recorded"]

    @recorded.setter
    def recorded(self, value: list[str]) -> None:
        self._pool()["recorded"] = list(value)

    @property
    def enabled(self) -> list[str]:
        return self._pool()["enabled"]

    @enabled.setter
    def enabled(self, value: list[str]) -> None:
        self._pool()["enabled"] = list(value)


def normalize_tag(raw: str) -> str:
    """Booru-style: lowercase, spaces → underscores, strip."""
    t = " ".join((raw or "").strip().split()).replace(" ", "_").casefold()
    # Drop a leading '-' so negatives are stored as plain names.
    while t.startswith("-"):
        t = t[1:].lstrip()
    return t


def _clean_tag_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = normalize_tag(str(item or ""))
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _load_one_pool(raw: object) -> dict[str, list[str]]:
    pool = _empty_pool()
    if not isinstance(raw, dict):
        return pool
    recorded = _clean_tag_list(raw.get("recorded"))
    pool["recorded"] = recorded
    allowed = set(recorded)
    if "enabled" in raw:
        pool["enabled"] = [t for t in _clean_tag_list(raw.get("enabled")) if t in allowed]
    else:
        pool["enabled"] = list(recorded)
    return pool


def load_combo() -> ComboState:
    state = ComboState()
    if not COMBO_PATH.exists():
        return state
    try:
        raw = json.loads(COMBO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return state
    if not isinstance(raw, dict):
        return state

    mode = str(raw.get("mode") or "danbooru").strip().lower()
    state.mode = "rule34" if mode == "rule34" else "danbooru"
    rating = str(raw.get("rating") or "").strip().lower()
    state.rating = rating if rating in ("g", "s", "q", "e") else ""
    negs = _clean_tag_list(raw.get("r34_negatives"))
    state.r34_negatives = negs if negs or "r34_negatives" in raw else list(
        DEFAULT_R34_NEGATIVES
    )

    pools = _empty_pools()
    raw_pools = raw.get("pools")
    if isinstance(raw_pools, dict):
        for key in ("danbooru", "rule34"):
            if key in raw_pools:
                pools[key] = _load_one_pool(raw_pools.get(key))
    elif "recorded" in raw:
        # Legacy single pool was built for Danbooru — keep it there; R34 starts empty.
        pools["danbooru"] = _load_one_pool(
            {"recorded": raw.get("recorded"), "enabled": raw.get("enabled")}
            if "enabled" in raw
            else {"recorded": raw.get("recorded")}
        )
    state.pools = pools
    # Persist migrated shape so R34 never silently shares the Danbooru list.
    if not isinstance(raw_pools, dict) and "recorded" in raw:
        try:
            save_combo(state)
        except OSError:
            pass
    return state


def save_combo(state: ComboState) -> None:
    for key in ("danbooru", "rule34"):
        pool = state._pool(key)  # type: ignore[arg-type]
        allowed = set(pool["recorded"])
        pool["enabled"] = [t for t in pool["enabled"] if t in allowed]
    payload = {
        "mode": state.mode,
        "rating": state.rating if state.mode == "danbooru" else "",
        "r34_negatives": list(state.r34_negatives),
        "pools": {
            "danbooru": {
                "recorded": list(state._pool("danbooru")["recorded"]),
                "enabled": list(state._pool("danbooru")["enabled"]),
            },
            "rule34": {
                "recorded": list(state._pool("rule34")["recorded"]),
                "enabled": list(state._pool("rule34")["enabled"]),
            },
        },
    }
    COMBO_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def add_recorded(state: ComboState, raw: str) -> str | None:
    """Add a recorded tag (On by default). Returns name, or None if empty/dup."""
    name = normalize_tag(raw)
    if not name or name in state.recorded:
        return None
    state.recorded.append(name)
    if name not in state.enabled:
        state.enabled.append(name)
    save_combo(state)
    return name


def remove_recorded(state: ComboState, name: str) -> bool:
    clean = normalize_tag(name)
    if clean not in state.recorded:
        return False
    state.recorded = [t for t in state.recorded if t != clean]
    state.enabled = [t for t in state.enabled if t != clean]
    save_combo(state)
    return True


def set_recorded_enabled(state: ComboState, name: str, on: bool) -> bool:
    """Toggle whether a recorded partner is used in Open all combos."""
    clean = normalize_tag(name)
    if clean not in state.recorded:
        return False
    if on:
        if clean not in state.enabled:
            state.enabled.append(clean)
    else:
        state.enabled = [t for t in state.enabled if t != clean]
    save_combo(state)
    return True


def set_many_recorded_enabled(
    state: ComboState, names: list[str], on: bool
) -> int:
    """Enable or disable several recorded partners. Returns how many changed."""
    changed = 0
    for raw in names:
        clean = normalize_tag(raw)
        if clean not in state.recorded:
            continue
        was = clean in state.enabled
        if on and not was:
            state.enabled.append(clean)
            changed += 1
        elif not on and was:
            state.enabled = [t for t in state.enabled if t != clean]
            changed += 1
    if changed:
        save_combo(state)
    return changed


def is_recorded_enabled(state: ComboState, name: str) -> bool:
    return normalize_tag(name) in state.enabled


def recorded_tags_text(state: ComboState) -> str:
    """One recorded tag per line (for the copyable list window)."""
    return "\n".join(state.recorded)


def set_mode(state: ComboState, mode: Mode) -> None:
    state.mode = "rule34" if mode == "rule34" else "danbooru"
    save_combo(state)


def set_rating(state: ComboState, rating: Rating) -> None:
    state.rating = rating if rating in ("g", "s", "q", "e") else ""
    save_combo(state)


def set_r34_negatives(state: ComboState, tags: list[str]) -> None:
    state.r34_negatives = _clean_tag_list(tags)
    save_combo(state)


def add_r34_negative(state: ComboState, raw: str) -> str | None:
    name = normalize_tag(raw)
    if not name or name in state.r34_negatives:
        return None
    state.r34_negatives.append(name)
    save_combo(state)
    return name


def remove_r34_negative(state: ComboState, name: str) -> bool:
    clean = normalize_tag(name)
    if clean not in state.r34_negatives:
        return False
    state.r34_negatives = [t for t in state.r34_negatives if t != clean]
    save_combo(state)
    return True


def posts_search_url(mode: Mode, tags: list[str]) -> str:
    joined = " ".join(t for t in tags if t)
    encoded = quote(joined, safe="")
    if mode == "rule34":
        return f"{R34_SITE}/index.php?page=post&s=list&tags={encoded}"
    return f"{DANBOORU_BASE}/posts?tags={encoded}"


def build_combo_queries(
    input_tag: str,
    state: ComboState,
) -> list[tuple[str, str]]:
    """Return ``(display_query, url)`` for each input+recorded pair.

    Skips the pair when the recorded tag equals the input tag.
    """
    seed = normalize_tag(input_tag)
    if not seed:
        return []
    enabled = set(state.enabled)
    out: list[tuple[str, str]] = []
    for recorded in state.recorded:
        if recorded not in enabled:
            continue
        if recorded == seed:
            continue
        parts = [seed, recorded]
        if state.mode == "danbooru" and state.rating:
            parts.append(f"rating:{state.rating}")
        elif state.mode == "rule34":
            parts.extend(f"-{n}" for n in state.r34_negatives)
        query = " ".join(parts)
        out.append((query, posts_search_url(state.mode, parts)))
    return out
