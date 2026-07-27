from __future__ import annotations

import re


def format_character_name(tag: str) -> str:
    """kaga_(kancolle) -> Kaga (series suffix hidden in UI; full tag kept in DB)."""
    if not tag or tag.strip() in ("unknown", "animated", "?"):
        return "С трассы"
    tag = tag.strip()
    m = re.match(r"^(.+?)_\((.+)\)$", tag)
    if m:
        suffix = m.group(2).lower()
        if suffix == "cosplay":
            return f"{_title(m.group(1))} (cosplay)"
        return _title(m.group(1))
    return _title(tag)


def _title(s: str) -> str:
    s = s.replace("_", " ")
    return " ".join(part.capitalize() for part in s.split() if part)


def format_artist_name(tag: str) -> str:
    if not tag or tag.strip() in ("unknown", "?", ""):
        return ""
    return _title(tag.strip().replace(" ", "_"))


def character_display_tag(char: dict) -> str:
    for tag in (char.get("canonical_tag"), char.get("character_tag")):
        if tag and tag.strip() not in ("unknown", "animated", "?", ""):
            return tag
    return "unknown"


def character_name_html(tag: str) -> str:
    import html as html_mod

    return f"<b>{html_mod.escape(format_character_name(tag))}</b>"


def character_name_html_from_char(char: dict) -> str:
    return character_name_html(character_display_tag(char))


def telegram_message_link(chat_id: int | None, message_id: int | None) -> str | None:
    """Supergroup message URL (t.me/c/...). None when link cannot be built."""
    if not chat_id or not message_id:
        return None
    cid, mid = int(chat_id), int(message_id)
    if mid <= 0:
        return None
    raw = str(cid)
    if raw.startswith("-100") and len(raw) > 4:
        return f"https://t.me/c/{raw[4:]}/{mid}"
    return None
