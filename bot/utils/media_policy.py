"""Media URL policy — thumb vs send URLs for inline grid and chat."""
from __future__ import annotations

import re

from bot.utils.media_urls import hell_send_url, url_ext

STATIC_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "webp"})
INLINE_ANIM_EXTS = frozenset({"gif", "mp4"})
SKIP_EXTS = frozenset({"swf", "webm", "zip", ""})

_LEGACY_DANBOORU_PREVIEW = re.compile(
    r"^https://danbooru\.donmai\.us/preview/\d+\.jpg$", re.I
)


def is_static_image_ext(ext: str) -> bool:
    return ext in STATIC_IMAGE_EXTS


def is_inline_anim_ext(ext: str) -> bool:
    return ext in INLINE_ANIM_EXTS


def is_usable_ext(ext: str) -> bool:
    return ext not in SKIP_EXTS


def is_legacy_danbooru_preview(url: str) -> bool:
    """Guessed /preview/{id}.jpg paths — 404 on modern Danbooru."""
    return bool(_LEGACY_DANBOORU_PREVIEW.match((url or "").split("?")[0].strip()))


def _url_has_anim_marker(url: str) -> bool:
    low = (url or "").lower()
    return ".gif" in low or ".mp4" in low


def _stored_url(char: dict, key: str, *, allow_anim: bool = False) -> str:
    url = (char.get(key) or "").strip()
    if not url.startswith("http") or is_legacy_danbooru_preview(url):
        return ""
    ext = url_ext(url)
    if ext in SKIP_EXTS:
        return ""
    if is_inline_anim_ext(ext):
        return url if allow_anim else ""
    if is_static_image_ext(ext):
        return url
    return ""


def _first_anim_url(char: dict) -> str:
    for key in ("file_url", "image_url"):
        url = _stored_url(char, key, allow_anim=True)
        if not url:
            continue
        ext = url_ext(url)
        if is_inline_anim_ext(ext) or _url_has_anim_marker(url):
            return url
    return ""


def is_animated_char(char: dict) -> bool:
    return bool(_first_anim_url(char))


def media_ext(char: dict) -> str:
    for key in ("file_url", "image_url"):
        ext = url_ext((char.get(key) or "").strip())
        if ext and is_usable_ext(ext):
            return ext
    combined = f"{char.get('file_url') or ''} {char.get('image_url') or ''}".lower()
    if ".gif" in combined:
        return "gif"
    if ".mp4" in combined:
        return "mp4"
    return url_ext(inline_send_url(char))


def thumb_url(char: dict) -> str:
    """Static thumb from stored URLs — never legacy /preview/{id}.jpg guesses."""
    if char.get("source") == "hell":
        from bot.utils.media_urls import r34_hell_thumb_url

        return r34_hell_thumb_url(char) or ""

    for key in ("preview_url", "image_url", "file_url"):
        url = _stored_url(char, key, allow_anim=False)
        if url:
            return url

    from bot.utils.media_urls import danbooru_static_thumb_url

    return danbooru_static_thumb_url(char) or ""


def inline_grid_thumb_url(char: dict) -> str:
    """Thumbnail for grid tiles and list Article rows — static JPEG/PNG only."""
    thumb = thumb_url(char)
    if thumb:
        return thumb
    send = inline_send_url(char)
    if send and is_static_image_ext(url_ext(send)):
        return send
    return ""


def mpeg4_needs_thumb(char: dict) -> bool:
    if inline_result_kind(char) != "mpeg4":
        return False
    preview = (char.get("preview_url") or "").strip()
    if (
        preview
        and is_static_image_ext(url_ext(preview))
        and not is_legacy_danbooru_preview(preview)
    ):
        return False
    if thumb_url(char):
        return False
    if char.get("source") == "hell":
        from bot.utils.media_urls import r34_hell_thumb_url

        return not bool(r34_hell_thumb_url(char))
    from bot.utils.media_urls import danbooru_static_thumb_url

    return not bool(danbooru_static_thumb_url(char))


def needs_inline_media_repair(char: dict) -> bool:
    """True when Danbooru/r34 URLs should be refreshed from post_id."""
    if not char.get("post_id"):
        return False
    for key in ("file_url", "image_url"):
        if url_ext((char.get(key) or "").strip()) == "zip":
            return True
    kind = inline_result_kind(char)
    if not kind:
        from bot.utils.media_urls import has_stored_animation_url

        return is_animated_char(char) or has_stored_animation_url(char)
    if kind == "mpeg4":
        return mpeg4_needs_thumb(char)
    return False


def _danbooru_inline_send(char: dict) -> str:
    anim = _first_anim_url(char)
    if anim:
        return anim
    for key in ("file_url", "image_url"):
        url = _stored_url(char, key, allow_anim=False)
        if url:
            return url
    return ""


def inline_send_url(char: dict) -> str:
    """Full-quality URL when an inline result is chosen."""
    anim = _first_anim_url(char)
    if anim:
        return anim
    if char.get("source") == "hell":
        send = hell_send_url(char)
        if send and is_usable_ext(url_ext(send)) and not is_legacy_danbooru_preview(send):
            return send
        img = _stored_url(char, "image_url", allow_anim=True)
        return img or (char.get("image_url") or "").strip()
    return _danbooru_inline_send(char)


def chat_send_url(char: dict) -> str:
    return inline_send_url(char)


def inline_grid_photo_url(char: dict) -> str:
    """Grid/list photo — full file by default; JPG /original/ only uses stored sample."""
    send = inline_send_url(char)
    if inline_result_kind(char) != "photo":
        return send
    if url_ext(send) not in ("jpg", "jpeg"):
        return send
    if "/original/" not in send.lower():
        return send
    sample = (char.get("image_url") or "").strip()
    if (
        sample
        and sample != send
        and "/sample/" in sample.lower()
        and is_static_image_ext(url_ext(sample))
    ):
        return sample
    return send


def list_post_url(char: dict) -> str:
    """Same media URL grid sends — never a 404 preview link."""
    if inline_result_kind(char) == "photo":
        return inline_grid_photo_url(char)
    return inline_send_url(char)


def list_thumb_url(char: dict) -> str:
    return list_article_thumb_url(char)


def list_article_thumb_url(char: dict) -> str:
    """JPEG-first thumb for inline list Article rows (Telegram list preview)."""
    if char.get("source") == "hell":
        from bot.utils.media_urls import r34_hell_thumb_url, r34_sample_url, r34_thumbnail_url

        thumb = r34_hell_thumb_url(char)
        if thumb:
            return thumb
        post_id = char.get("post_id")
        if post_id:
            return r34_sample_url(int(post_id)) or r34_thumbnail_url(int(post_id))
        return ""

    preview = (char.get("preview_url") or "").strip()
    if (
        preview
        and url_ext(preview) in ("jpg", "jpeg")
        and not is_legacy_danbooru_preview(preview)
    ):
        return preview

    from bot.utils.media_urls import (
        danbooru_jpg_variant,
        danbooru_preview_jpg_for_post,
        danbooru_sample_jpg_from_url,
    )

    for key in ("file_url", "image_url"):
        raw = (char.get(key) or "").strip()
        sample = danbooru_sample_jpg_from_url(raw)
        if sample:
            return sample
        variant = danbooru_jpg_variant(raw)
        if variant:
            return variant

    base = thumb_url(char)
    if base and url_ext(base) in ("jpg", "jpeg"):
        return base

    send = inline_send_url(char)
    if send and url_ext(send) in ("jpg", "jpeg"):
        return send

    # Legacy /preview/{id}.jpg — still fine for list tiles on many older cards.
    if preview and url_ext(preview) in ("jpg", "jpeg"):
        return preview

    post_id = char.get("post_id")
    if post_id:
        return danbooru_preview_jpg_for_post(int(post_id))

    # PNG/WebP last — better than nothing for some clients.
    if base:
        return base
    if send and is_static_image_ext(url_ext(send)):
        return send
    return ""


def list_embed_url(char: dict) -> str:
    """URL for list Article link preview — Telegram-prefetchable display file."""
    kind = inline_result_kind(char)
    if kind in ("gif", "mpeg4"):
        return ""
    url = inline_grid_photo_url(char) if kind == "photo" else inline_send_url(char)
    if url and not is_legacy_danbooru_preview(url):
        return url
    return ""


def inline_result_kind(char: dict) -> str:
    url = inline_send_url(char)
    if not url:
        return ""
    ext = media_ext(char) or url_ext(url)
    if not is_usable_ext(ext):
        return ""
    if ext == "gif":
        return "gif"
    if ext == "mp4":
        return "mpeg4"
    if is_static_image_ext(ext):
        return "photo"
    return ""
