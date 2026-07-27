from __future__ import annotations

from urllib.parse import urlparse


def url_ext(url: str) -> str:
    path = urlparse((url or "").split("?")[0]).path.lower()
    if "." not in path:
        return ""
    return path.rsplit(".", 1)[-1]


SKIP_ACQUIRE_EXTS = frozenset({"webm", "swf", "zip"})
_STATIC_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "webp"})


def _is_static_image_url(url: str) -> bool:
    return url_ext((url or "").strip()) in _STATIC_IMAGE_EXTS


def is_blocked_media_url(url: str) -> bool:
    """True for formats we never store (caller should pull again)."""
    return url_ext((url or "").strip()) in SKIP_ACQUIRE_EXTS


def has_blocked_media_urls(char: dict) -> bool:
    for key in ("image_url", "file_url", "preview_url"):
        if is_blocked_media_url((char.get(key) or "").strip()):
            return True
    return False


def prepare_storable_fields(fields: dict) -> dict | None:
    """Drop blocked preview URLs; return None if main media is blocked."""
    out = dict(fields)
    for key in ("image_url", "file_url"):
        if is_blocked_media_url((out.get(key) or "").strip()):
            return None
    prev = (out.get("preview_url") or "").strip()
    if is_blocked_media_url(prev):
        fallback = (out.get("image_url") or out.get("file_url") or "").strip()
        if is_blocked_media_url(fallback):
            out["preview_url"] = ""
        else:
            out["preview_url"] = fallback
    return out


def has_stored_animation_url(char: dict) -> bool:
    """True when image_url/file_url point at gif/mp4 (not preview jpeg)."""
    for key in ("file_url", "image_url"):
        url = (char.get(key) or "").strip()
        if not url:
            continue
        ext = url_ext(url)
        if ext in ("gif", "mp4"):
            return True
        low = url.lower()
        if ".gif" in low or ".mp4" in low:
            return True
    return False


def is_broken_animated_card(char: dict) -> bool:
    """Animated roster entry without a real gif/mp4 URL (e.g. webm downgraded to jpeg)."""
    source = (char.get("source") or "").strip()
    if source not in ("animated", "admin_seed_animated"):
        return False
    return not has_stored_animation_url(char)


def might_be_webm_orphan(char: dict) -> bool:
    """Static sample/preview URLs only — possible webm post stored as jpeg."""
    if has_stored_animation_url(char) or has_blocked_media_urls(char):
        return False
    if not char.get("post_id") or (char.get("source") or "") == "hell":
        return False
    if is_broken_animated_card(char):
        return True
    source = (char.get("source") or "").strip()
    if source != "roll":
        return False
    image = (char.get("image_url") or "").strip().lower()
    file_url = (char.get("file_url") or "").strip().lower()
    sampleish = "/sample/" in image or "/preview/" in image
    if not sampleish:
        return False
    if not file_url or "/sample/" in file_url or "/preview/" in file_url:
        return True
    return False


def is_r34_lowres_url(url: str) -> bool:
    u = (url or "").lower()
    return "/thumbnail" in u or "/preview" in u or "/samples/" in u


def needs_r34_url_refresh(char: dict) -> bool:
    if char.get("source") != "hell" or not char.get("post_id"):
        return False
    image = (char.get("image_url") or "").strip()
    file_url = (char.get("file_url") or "").strip()
    if is_r34_lowres_url(image):
        return True
    img_ext = url_ext(image)
    file_ext = url_ext(file_url)
    if file_ext in ("gif", "mp4", "webm") and img_ext not in ("gif", "mp4", "webm"):
        return True
    return False


def r34_post_send_url(post) -> str:
    """Best Telegram-sendable URL for a rule34 post."""
    file_url = (getattr(post, "file_url", None) or "").strip()
    image_url = (getattr(post, "image_url", None) or "").strip()
    preview = (getattr(post, "preview_url", None) or "").strip()
    for url in (file_url, image_url):
        if url and _telegram_ok(url):
            return url
    for url in (preview, image_url, file_url):
        if url and _telegram_ok(url):
            return url
    return image_url or file_url or preview


def r34_storage_fields(post) -> dict:
    send = r34_post_send_url(post)
    file_url = (getattr(post, "file_url", None) or "").strip() or send
    sample = (getattr(post, "sample_url", None) or "").strip()
    preview = (getattr(post, "preview_url", None) or "").strip()
    pid = int(getattr(post, "post_id", 0) or 0)
    if sample and _is_static_image_url(sample):
        preview = sample
    elif pid:
        preview = _fix_r34_preview_url(preview, pid)
    if not preview or preview == send:
        if pid > 0:
            thumb = r34_thumbnail_url(pid)
            if thumb:
                preview = thumb
    if not preview:
        preview = send
    return {
        "image_url": send,
        "file_url": file_url,
        "preview_url": preview,
        "post_id": post.post_id,
    }


def char_display_url(char: dict) -> str:
    if char.get("source") == "hell":
        return hell_send_url(char) or (char.get("image_url") or "").strip()
    return (char.get("file_url") or char.get("image_url") or "").strip()


def _telegram_ok(url: str) -> bool:
    import re

    url = url.lower().split("?")[0]
    if any(x in url for x in (".swf", ".zip")):
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|gif|webp|mp4)$", url))


def r34_thumbnail_url(post_id: int) -> str:
    """Standard rule34 preview JPEG — Telegram-inline-safe."""
    pid = int(post_id)
    if pid <= 0:
        return ""
    return f"https://img.rule34.xxx/thumbnail/{pid // 1000}/thumbnail_{pid}.jpg"


def r34_sample_url(post_id: int) -> str:
    """Rule34 sample JPEG — better mp4 grid tile than grey thumbnail."""
    pid = int(post_id)
    if pid <= 0:
        return ""
    return f"https://img.rule34.xxx/samples/{pid // 1000}/sample_{pid}.jpg"


def danbooru_jpg_variant(url: str) -> str:
    """sample-123.png on the same host often has a matching .jpg for list previews."""
    url = (url or "").strip()
    ext = url_ext(url)
    if ext not in ("png", "webp") or "sample" not in url.lower():
        return ""
    return f"{url.rsplit('.', 1)[0]}.jpg"


def danbooru_preview_jpg_for_post(post_id: int | None) -> str:
    pid = int(post_id or 0)
    if pid <= 0:
        return ""
    return f"https://danbooru.donmai.us/preview/{pid}.jpg"


def danbooru_sample_jpg_from_md5(md5: str) -> str:
    md5 = (md5 or "").strip().lower()
    if len(md5) != 32:
        return ""
    return f"https://cdn.donmai.us/sample/{md5[:2]}/{md5[2:4]}/sample-{md5}.jpg"


def danbooru_md5_from_url(url: str) -> str:
    import re

    url = url or ""
    m = re.search(r"sample-([a-f0-9]{32})\.", url, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"/([a-f0-9]{32})(?:\.[a-z0-9]+)?(?:\?|$|/)", url, re.I)
    return m.group(1).lower() if m else ""


def danbooru_sample_jpg_from_url(url: str) -> str:
    md5 = danbooru_md5_from_url(url)
    return danbooru_sample_jpg_from_md5(md5) if md5 else ""


def danbooru_static_thumb_url(char: dict) -> str:
    """JPEG/PNG thumb for Danbooru mp4/gif inline — derived from md5 when needed."""
    if (char.get("source") or "") == "hell":
        return ""
    from bot.utils.media_policy import is_legacy_danbooru_preview

    for key in ("preview_url", "image_url", "file_url"):
        url = (char.get(key) or "").strip()
        if not url or is_legacy_danbooru_preview(url):
            continue
        if _is_static_image_url(url):
            return url
    for key in ("file_url", "image_url"):
        sample = danbooru_sample_jpg_from_url((char.get(key) or "").strip())
        if sample:
            return sample
    return ""


def _char_is_mp4(char: dict) -> bool:
    for key in ("file_url", "image_url"):
        if url_ext((char.get(key) or "").strip()) == "mp4":
            return True
    return False


def _fix_r34_preview_url(url: str, post_id: int | None) -> str:
    """Rewrite legacy broken /thumbnails/ URLs to the live /thumbnail/ path."""
    if not url or not post_id:
        return url
    if "/thumbnails/" in url.lower():
        return r34_thumbnail_url(int(post_id))
    return url


def r34_hell_thumb_url(char: dict) -> str:
    """Best static thumb for hell inline grid (stored preview or rule34 thumbnail)."""
    post_id = char.get("post_id")
    preview = _fix_r34_preview_url((char.get("preview_url") or "").strip(), post_id)
    if preview and _is_static_image_url(preview):
        if "/samples/" in preview.lower():
            return preview
        if not _char_is_mp4(char):
            return preview
    if post_id and _char_is_mp4(char):
        sample = r34_sample_url(int(post_id))
        if sample:
            return sample
    if post_id:
        return r34_thumbnail_url(int(post_id))
    return ""


def hell_inline_photo_url(char: dict) -> str:
    """Telegram inline grid — sample/preview/thumbnail (not huge file URLs)."""
    preview = (char.get("preview_url") or "").strip()
    image = (char.get("image_url") or "").strip()
    for url in (preview, image):
        if url and _telegram_ok(url):
            return url
    post_id = char.get("post_id")
    if post_id:
        thumb = r34_thumbnail_url(int(post_id))
        if thumb and _telegram_ok(thumb):
            return thumb
    return image


def hell_send_url(char: dict) -> str:
    """Best Telegram-sendable URL for a hell card (full file, else sample)."""
    for key in ("file_url", "image_url"):
        url = (char.get(key) or "").strip()
        ext = url_ext(url)
        if url and _telegram_ok(url) and not is_r34_lowres_url(url) and ext in ("gif", "mp4"):
            return url
    for key in ("file_url", "image_url"):
        url = (char.get(key) or "").strip()
        if url and _telegram_ok(url) and not is_r34_lowres_url(url):
            return url
    for key in ("file_url", "image_url"):
        url = (char.get(key) or "").strip()
        if url and _telegram_ok(url):
            return url
    return (char.get("image_url") or "").strip()


def booru_post_page_url(
    post_id: int | None,
    *,
    source: str = "",
    gender: str = "",
) -> str:
    """Danbooru / rule34 post page (tags, artist, etc.) — not a direct image link."""
    pid = int(post_id or 0)
    if pid <= 0:
        return ""
    if source == "hell" or gender == "hell":
        return f"https://rule34.xxx/index.php?page=post&s=view&id={pid}"
    return f"https://danbooru.donmai.us/posts/{pid}"


def full_res_url(char: dict) -> str:
    """Direct original file when stored; else post page on the host."""
    file_url = (char.get("file_url") or "").strip()
    if file_url:
        return file_url
    post_id = char.get("post_id")
    if post_id:
        if char.get("source") == "hell":
            return booru_post_page_url(post_id, source="hell")
        return booru_post_page_url(post_id)
    return (char.get("image_url") or "").strip()
