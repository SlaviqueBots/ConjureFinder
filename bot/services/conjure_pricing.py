from __future__ import annotations

from typing import TYPE_CHECKING

from bot.core.config import CONJURE_PRICE_GENERAL, CONJURE_PRICE_PREMIUM
from bot.utils.booru_tags import is_meta_search_tag
from bot.utils.currency import MoneyStyle, format_with_style

if TYPE_CHECKING:
    from bot.services.danbooru import DanbooruClient
    from bot.services.rule34 import Rule34Client

# Danbooru / gelbooru: 0 general, 1 artist, 3 copyright, 4 character, 5 meta
PREMIUM_TAG_CATEGORIES = frozenset({1, 3, 4})

# General/meta tags that unlock animated content — premium even at 50 on paper.
PREMIUM_GENERAL_TAGS = frozenset({
    "animated",
    "animation",
    "gif",
    "gifs",
    "video",
    "videos",
    "webm",
    "mp4",
    "voice_acted",
    "voice",
    "sound",
    "audio",
    "with_sound",
    "with_audio",
    "sound_warning",
})

_TAG_PREFIXES = (
    "character:",
    "char:",
    "copyright:",
    "copy:",
    "artist:",
    "general:",
    "gen:",
    "meta:",
)

_CATEGORY_LABELS = {
    0: "общий",
    1: "артист",
    3: "серия",
    4: "персонаж",
    5: "мета",
}


def normalize_conjure_tag(tag: str) -> str:
    tag = tag.strip().lower()
    for prefix in _TAG_PREFIXES:
        if tag.startswith(prefix):
            return tag[len(prefix) :]
    return tag


def conjure_price_for_tag(name: str, category: int | None) -> int:
    name = normalize_conjure_tag(name)
    if name in PREMIUM_GENERAL_TAGS or "(cosplay)" in name:
        return CONJURE_PRICE_PREMIUM
    if category is None:
        return CONJURE_PRICE_PREMIUM
    if category in PREMIUM_TAG_CATEGORIES:
        return CONJURE_PRICE_PREMIUM
    return CONJURE_PRICE_GENERAL


def tag_category_label(category: int | None) -> str:
    if category is None:
        return "?"
    return _CATEGORY_LABELS.get(category, "общий")


def conjure_tag_kind_label(name: str, category: int | None, price: int) -> str:
    name = normalize_conjure_tag(name)
    if name in PREMIUM_GENERAL_TAGS:
        return "аним./медиа"
    if "(cosplay)" in name:
        return "косплей"
    if category is None:
        return "неизвестный"
    return _CATEGORY_LABELS.get(category, "общий")


CHARACTER_TAG_CATEGORY = 4


async def pick_conjure_name_tag(
    tags: list[str],
    *,
    danbooru: DanbooruClient | None = None,
    rule34: Rule34Client | None = None,
) -> str | None:
    """Character tag(s) in a conjure query — permanent card name."""
    if not tags:
        return None
    char_tags: list[str] = []
    for raw in tags:
        name = normalize_conjure_tag(raw)
        if not name or is_meta_search_tag(name):
            continue
        category = await _lookup_tag_category(name, danbooru=danbooru, rule34=rule34)
        if category == CHARACTER_TAG_CATEGORY:
            char_tags.append(name)
    if not char_tags:
        return None
    if len(char_tags) == 1:
        return char_tags[0]
    if danbooru:
        return await danbooru.pick_popular_character_tag(char_tags)
    return char_tags[0]


async def _lookup_tag_category(
    name: str,
    *,
    danbooru: DanbooruClient | None,
    rule34: Rule34Client | None,
) -> int | None:
    if danbooru:
        cat = await danbooru.tag_category(name)
        if cat is not None:
            return cat
    if rule34 and rule34.api_ready:
        return await rule34.tag_category(name)
    return None


async def conjure_price_breakdown(
    tags: list[str],
    *,
    danbooru: DanbooruClient | None = None,
    rule34: Rule34Client | None = None,
    money_style: MoneyStyle | None = None,
) -> tuple[list[str], int]:
    from bot.utils.currency import pick_money_style

    style = money_style or pick_money_style()
    lines: list[str] = []
    total = 0
    for raw in tags:
        name = normalize_conjure_tag(raw)
        category = await _lookup_tag_category(name, danbooru=danbooru, rule34=rule34)
        price = conjure_price_for_tag(name, category)
        total += price
        kind = conjure_tag_kind_label(name, category, price)
        lines.append(
            f"• <code>{raw}</code> — {format_with_style(price, style)} ({kind})"
        )
    return lines, total


async def total_conjure_price(
    tags: list[str],
    *,
    danbooru: DanbooruClient | None = None,
    rule34: Rule34Client | None = None,
) -> int:
    _, total = await conjure_price_breakdown(tags, danbooru=danbooru, rule34=rule34)
    return total
