"""Fetch posts from rule34.xxx via authenticated API or HTML scrape fallback."""
from __future__ import annotations

import asyncio
import html
import logging
import random
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import unquote_plus

import httpx

import bot.core.config as _config
from bot.utils.media_urls import is_blocked_media_url
from bot.utils.r34_tags import build_r34_query, build_r34_random_query, normalize_r34_tag

logger = logging.getLogger(__name__)


class _LiveCfg:
    """Always read the current Config — Settings reload rebinds bot.core.config.CFG."""

    def __getattr__(self, name: str):
        return getattr(_config.CFG, name)


CFG = _LiveCfg()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
API = "https://api.rule34.xxx/index.php"
VIEW = "https://rule34.xxx/index.php?page=post&s=view&id={post_id}"
MAX_POST_ID = 12_000_000
MIN_POST_ID = 1

_IMG_RE = re.compile(
    r'(https?://(?:wimg|img)\.rule34\.xxx/+images/[^"\']+\.(?:jpg|jpeg|png|gif|webp|mp4|webm))',
    re.I,
)
_LI_RE = re.compile(
    r'<li class="tag-type-(character|copyright|general|artist)[^"]*"[^>]*>(.*?)</li>',
    re.I | re.S,
)
_TAGS_HREF = re.compile(
    r'page=post(?:&amp;|&)s=list(?:&amp;|&)tags=([^"&]+)',
    re.I,
)

_SKIP = frozenset({
    "1girl", "1boy", "2girls", "2boys", "3girls", "3boys", "solo", "duo", "trio",
    "highres", "absurdres", "commentary_request", "translated", "english_text",
    "comic", "animated", "gif", "video", "sound", "tagme", "?",
})

RATING_TAG = {
    "G": "rating:safe",
    "S": "rating:questionable",
    "Q": "rating:questionable",
    "E": "rating:explicit",
}


def _parse_tag_index_payload(raw: bytes | str) -> list[dict]:
    """Rule34 tag index often returns XML even when ``json=1`` is requested."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        import json

        data = json.loads(text)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            return [data]
        return []
    root = ET.fromstring(text)
    rows: list[dict] = []
    for node in root.iter("tag"):
        name = (node.get("name") or "").strip()
        if not name:
            continue
        typ = node.get("type", node.get("category", "0"))
        count = node.get("count", "0")
        try:
            type_i = int(typ)
        except (TypeError, ValueError):
            type_i = 0
        try:
            count_i = int(count)
        except (TypeError, ValueError):
            count_i = 0
        rows.append({"name": name, "type": type_i, "category": type_i, "count": count_i})
    return rows


def _post_acquirable(post: Rule34Post) -> bool:
    for url in (post.file_url, post.image_url):
        if is_blocked_media_url(url or ""):
            return False
    return True


@dataclass
class Rule34Post:
    post_id: int
    image_url: str
    preview_url: str
    file_url: str = ""
    sample_url: str = ""
    tags: str = ""
    character_tag: str = ""
    artist_tag: str = ""
    width: int = 0
    height: int = 0
    rating: str = "e"  # g/s/q/e letter used by reshape buttons
    character_tag_candidates: tuple[str, ...] = ()
    artist_tags: tuple[str, ...] = ()
    copyright_tags: tuple[str, ...] = ()
    general_tags: tuple[str, ...] = ()
    meta_tags: tuple[str, ...] = ()


class Rule34Client:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._tag_category_cache: dict[str, int | None] = {}

    @property
    def api_ready(self) -> bool:
        return bool(CFG.rule34_api_key and CFG.rule34_user_id)

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": UA},
            timeout=30.0,
            follow_redirects=True,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    def _auth(self) -> dict[str, str]:
        return {
            "api_key": CFG.rule34_api_key,
            "user_id": str(CFG.rule34_user_id),
        }

    async def random_post(self, *, attempts: int = 5) -> Rule34Post | None:
        if self.api_ready:
            for _ in range(attempts):
                post = await self._api_random()
                if post and _post_acquirable(post):
                    return post
        assert self._client
        for _ in range(attempts):
            post_id = random.randint(MIN_POST_ID, MAX_POST_ID)
            post = await self._fetch_view(post_id)
            if post and _post_acquirable(post) and "ai_generated" not in (post.tags or "").split():
                return post
        return None

    async def random_by_tags(
        self,
        tags: str,
        exclude: set[str] | None = None,
        *,
        exclude_ids: set[int] | None = None,
        attempts: int = 10,
        exclude_ai: bool = True,
    ) -> Rule34Post | None:
        exclude = exclude or set()
        exclude_ids = exclude_ids or set()

        async def _search(*, with_ai_exclude: bool) -> Rule34Post | None:
            if not self.api_ready:
                return None
            if with_ai_exclude:
                query = build_r34_query(tags)
            else:
                parts: list[str] = []
                for token in (tags or "").split():
                    if token.startswith("-") or ":" in token:
                        parts.append(token.lower())
                    else:
                        parts.append(normalize_r34_tag(token))
                query = " ".join(parts)
            if not query:
                return None
            for attempt in range(attempts):
                # Small tag sets (e.g. artist with ~20 posts) only exist on page 0.
                pid = attempt if attempt < 6 else random.randint(0, 8)
                posts = await self._api_search(
                    query, pid=pid, limit=50, allow_ai=not with_ai_exclude
                )
                if not posts:
                    continue
                random.shuffle(posts)
                for post in posts:
                    if post.post_id in exclude_ids:
                        continue
                    if post.image_url in exclude:
                        continue
                    if post.preview_url and post.preview_url in exclude:
                        continue
                    if not _post_acquirable(post):
                        continue
                    return await self._enrich_character(post)
            return None

        post = await _search(with_ai_exclude=exclude_ai)
        if not post and exclude_ai:
            return await _search(with_ai_exclude=False)
        return post

    async def random_by_artist(
        self,
        artist_tag: str,
        exclude: set[str] | None = None,
        *,
        exclude_ids: set[int] | None = None,
        attempts: int = 15,
    ) -> Rule34Post | None:
        """Artist reshape — plain tag search, no -ai_generated filter."""
        exclude = exclude or set()
        exclude_ids = exclude_ids or set()
        query = normalize_r34_tag(artist_tag)
        if not query or not self.api_ready:
            return None
        for attempt in range(attempts):
            pid = attempt if attempt < 12 else random.randint(0, 20)
            posts = await self._api_search(
                query, pid=pid, limit=100, allow_ai=True
            )
            if not posts:
                continue
            random.shuffle(posts)
            for post in posts:
                if post.post_id in exclude_ids:
                    continue
                if post.image_url in exclude:
                    continue
                if post.preview_url and post.preview_url in exclude:
                    continue
                file_url = (getattr(post, "file_url", None) or "").strip()
                if file_url and file_url in exclude:
                    continue
                if not _post_acquirable(post):
                    continue
                return await self._enrich_character(post)
        return None

    async def fetch_by_id(self, post_id: int, *, allow_ai: bool = True) -> Rule34Post | None:
        """Reload post metadata from API (full file_url) or HTML fallback."""
        pid = int(post_id)
        if self.api_ready:
            posts = await self._api_search(
                f"id:{pid}", pid=0, limit=1, allow_ai=allow_ai
            )
            if posts:
                return await self._enrich_character(posts[0])
        return await self._fetch_view(pid)

    async def search_tags(self, tags: str, *, attempts: int = 5) -> Rule34Post | None:
        """Random post matching tag query (for /conjure_hell)."""
        if not self.api_ready:
            return None
        query = build_r34_query(tags.replace(",", " "))
        if not query:
            return None
        for attempt in range(attempts):
            pid = attempt if attempt < 3 else random.randint(0, 8)
            posts = await self._api_search(query, pid=pid, limit=30)
            if posts:
                return await self._enrich_character(random.choice(posts))
        return None

    async def tag_index_row(self, name: str) -> dict | None:
        """One tag-index lookup → ``{name, type/category, count}`` (XML or JSON)."""
        if not self.api_ready:
            return None
        name = name.strip().lower().replace(" ", "_")
        if not name:
            return None
        assert self._client
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._client.get(
                    API,
                    params={
                        **self._auth(),
                        "page": "dapi",
                        "s": "tag",
                        "q": "index",
                        "json": "1",
                        "name": name,
                        "limit": "10",
                    },
                )
                if r.status_code == 429 or r.status_code >= 500:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                if r.status_code != 200 or not r.content:
                    return None
                data = _parse_tag_index_payload(r.content)
                for row in data:
                    row_name = (row.get("name") or "").lower().replace(" ", "_")
                    if row_name == name:
                        try:
                            cat = int(row.get("type", row.get("category", 0)))
                            self._tag_category_cache[name] = cat
                        except (TypeError, ValueError):
                            pass
                        return row
                return None
            except Exception as exc:
                last_err = exc
                await asyncio.sleep(0.3 * (attempt + 1))
        if last_err:
            logger.debug("r34 tag_index_row %r failed: %s", name, last_err, exc_info=last_err)
        return None

    async def tag_category(self, name: str) -> int | None:
        """Gelbooru-style type: 0 general, 1 artist, 3 copyright, 4 character."""
        if not self.api_ready:
            return None
        name = name.strip().lower().replace(" ", "_")
        if not name:
            return None
        if name in self._tag_category_cache:
            return self._tag_category_cache[name]
        row = await self.tag_index_row(name)
        if not row:
            self._tag_category_cache[name] = None
            return None
        try:
            cat = int(row.get("type", row.get("category", 0)))
        except (TypeError, ValueError):
            cat = 0
        self._tag_category_cache[name] = cat
        return cat

    async def count_posts(self, tags: str) -> int:
        """Post count for a tag via dapi tag index, with search fallback."""
        if not self.api_ready:
            return 0
        name = normalize_r34_tag(tags)
        if not name:
            return 0
        n = await self._count_tag_index(name)
        if n > 0:
            return n
        return await self._count_posts_search(name)

    async def count_query_posts(self, tags: str) -> int:
        """Approximate post count for a possibly multi-tag query (pages search)."""
        if not self.api_ready:
            return 0
        q = (tags or "").strip()
        if not q:
            return 0
        return await self._count_posts_search(q)

    async def _count_tag_index(self, name: str) -> int:
        row = await self.tag_index_row(name)
        if not row:
            return 0
        try:
            return int(row.get("count") or 0)
        except (TypeError, ValueError):
            return 0

    async def _count_posts_search(self, name: str) -> int:
        """Count posts by paging search — reliable for small artist catalogs."""
        total = 0
        for pid in range(5):
            posts = await self._api_search(
                name, pid=pid, limit=100, allow_ai=True
            )
            if not posts:
                break
            total += len(posts)
            if len(posts) < 100:
                break
        return total

    async def suggest_tags(self, query: str, *, limit: int = 8) -> list[dict]:
        """Autocomplete similar tags via api.rule34.xxx/autocomplete.php."""
        query = query.strip().lower().replace(" ", "_")
        from bot.utils.booru_tags import is_valid_tag_query

        if not is_valid_tag_query(query):
            return []
        assert self._client
        try:
            r = await self._client.get(
                "https://api.rule34.xxx/autocomplete.php",
                params={"q": query},
            )
            if r.status_code != 200 or not r.content:
                return []
            data = r.json()
            if not isinstance(data, list):
                return []
            out: list[dict] = []
            for row in data[: limit * 2]:
                if isinstance(row, str):
                    name = row.strip()
                    cat = None
                elif isinstance(row, dict):
                    name = (row.get("value") or row.get("label") or row.get("name") or "").strip()
                    cat = row.get("type") or row.get("category")
                else:
                    continue
                if not name:
                    continue
                if cat is not None:
                    try:
                        self._tag_category_cache[name.lower()] = int(cat)
                    except (TypeError, ValueError):
                        pass
                out.append({"name": name, "category": cat, "count": 0})
            ranked = sorted(
                out,
                key=lambda x: (
                    0 if x["name"].lower().startswith(query) else 1,
                    x["name"].lower(),
                ),
            )
            return ranked[:limit]
        except Exception:
            logger.debug("r34 suggest %r failed", query, exc_info=True)
            return []

    async def _api_random(self) -> Rule34Post | None:
        query = build_r34_random_query()
        for _ in range(3):
            posts = await self._api_search(
                query, pid=random.randint(0, 30), limit=20
            )
            if posts:
                return await self._enrich_character(random.choice(posts))
        return None

    async def _api_search(
        self,
        tags: str,
        *,
        pid: int = 0,
        limit: int = 100,
        allow_ai: bool = False,
    ) -> list[Rule34Post]:
        """JSON search — caller supplies the final tags string."""
        assert self._client
        tags = (tags or "").strip()
        if not tags:
            return []
        try:
            r = await self._client.get(
                API,
                params={
                    **self._auth(),
                    "page": "dapi",
                    "s": "post",
                    "q": "index",
                    "json": "1",
                    "tags": tags,
                    "pid": pid,
                    "limit": min(limit, 100),
                },
            )
            if r.status_code != 200 or not r.content:
                return []
            data = r.json()
            if not isinstance(data, list):
                return []
            out: list[Rule34Post] = []
            for item in data:
                post = _post_from_api(item, allow_ai=allow_ai)
                if post:
                    out.append(post)
            return out
        except Exception:
            logger.debug("r34 api search tags=%r failed", tags, exc_info=True)
            return []

    async def _enrich_character(self, post: Rule34Post) -> Rule34Post:
        from bot.utils.media_urls import r34_storage_fields

        view = await self._fetch_view(post.post_id)
        fields = r34_storage_fields(post)
        artist = post.artist_tag
        tags = _normalize_tag_string(post.tags)
        char_tag = _normalize_tag_token(post.character_tag) or post.character_tag
        char_cands = list(post.character_tag_candidates)
        artist_tags = list(post.artist_tags)
        copyright_tags = list(post.copyright_tags)
        general_tags = list(post.general_tags)
        meta_tags = list(post.meta_tags)
        if view:
            if view.artist_tag and view.artist_tag != "unknown":
                artist = view.artist_tag
            tags = _normalize_tag_string(view.tags) or tags
            char_tag = _normalize_tag_token(view.character_tag) or char_tag
            if view.character_tag_candidates:
                char_cands = list(view.character_tag_candidates)
            if view.artist_tags:
                artist_tags = list(view.artist_tags)
            if view.copyright_tags:
                copyright_tags = list(view.copyright_tags)
            if view.general_tags:
                general_tags = list(view.general_tags)
            if view.meta_tags:
                meta_tags = list(view.meta_tags)
        if char_tag and char_tag.lower() not in ("unknown", "?"):
            if char_tag not in char_cands:
                char_cands.insert(0, char_tag)
        return Rule34Post(
            post_id=post.post_id,
            image_url=fields["image_url"],
            preview_url=fields["preview_url"],
            file_url=fields["file_url"],
            tags=tags,
            character_tag=char_tag,
            artist_tag=artist,
            width=post.width,
            height=post.height,
            rating=post.rating or (view.rating if view else "e"),
            character_tag_candidates=tuple(char_cands),
            artist_tags=tuple(artist_tags),
            copyright_tags=tuple(copyright_tags),
            general_tags=tuple(general_tags),
            meta_tags=tuple(meta_tags),
        )

    async def _fetch_view(self, post_id: int) -> Rule34Post | None:
        assert self._client
        try:
            r = await self._client.get(VIEW.format(post_id=post_id))
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                return None
            if "this post does not exist" in r.text.lower():
                return None
            matches = _IMG_RE.findall(r.text)
            if not matches:
                return None
            url = _clean_url(matches[0])
            if not _telegram_ok(url):
                return None
            parsed = _parse_tags_html_full(r.text)
            return Rule34Post(
                post_id=post_id,
                image_url=url,
                preview_url=url,
                file_url=url,
                tags=parsed["tags"],
                character_tag=parsed["character_tag"],
                artist_tag=parsed["artist_tag"],
                character_tag_candidates=tuple(parsed["characters"]),
                artist_tags=tuple(parsed["artists"]),
                copyright_tags=tuple(parsed["copyright"]),
                general_tags=tuple(parsed["general"]),
                meta_tags=tuple(parsed.get("meta", [])),
            )
        except Exception:
            logger.debug("r34 view id=%s failed", post_id, exc_info=True)
            return None


def rating_query_tag(rating: str) -> str:
    return RATING_TAG.get(rating.upper(), "rating:explicit")


def normalize_r34_rating_letter(raw: str | None) -> str:
    """Map Rule34/Gelbooru rating strings to g/s/q/e (Danbooru-style letters)."""
    r = (raw or "explicit").strip().lower()
    # Gelbooru letter ``s`` means safe; Danbooru ``s`` is sensitive.
    if r in ("g", "general", "safe", "s"):
        return "g"
    if r in ("q", "questionable"):
        return "q"
    if r in ("sensitive",):
        return "s"
    return "e"


def _post_from_api(item: dict, *, allow_ai: bool = False) -> Rule34Post | None:
    try:
        post_id = int(item.get("id") or 0)
    except (TypeError, ValueError):
        return None
    if post_id <= 0:
        return None
    full_url = _abs_url(item.get("file_url") or "")
    sample_url = _abs_url(
        item.get("sample_url") or item.get("jpeg_url") or ""
    )
    preview_url = _abs_url(item.get("preview_url") or "")
    if not full_url:
        full_url = sample_url
    tags_str = _normalize_tag_string(item.get("tags") or "")
    if not allow_ai and "ai_generated" in tags_str.split():
        return None
    char_tag, artist = _artist_from_tag_string(tags_str)
    rating = normalize_r34_rating_letter(item.get("rating"))
    post = Rule34Post(
        post_id=post_id,
        image_url="",
        preview_url=preview_url,
        file_url=full_url,
        sample_url=sample_url,
        tags=tags_str,
        character_tag="unknown",
        artist_tag=artist,
        width=int(item.get("width") or 0),
        height=int(item.get("height") or 0),
        rating=rating,
    )
    from bot.utils.media_urls import r34_storage_fields

    fields = r34_storage_fields(post)
    if not fields["image_url"]:
        return None
    return Rule34Post(
        post_id=post_id,
        image_url=fields["image_url"],
        preview_url=fields["preview_url"],
        file_url=fields["file_url"],
        sample_url=sample_url,
        tags=tags_str,
        character_tag="unknown",
        artist_tag=artist,
        width=post.width,
        height=post.height,
        rating=rating,
    )


def _artist_from_tag_string(tags_str: str) -> tuple[str, str]:
    if not tags_str:
        return "unknown", "unknown"
    artist = "unknown"
    for tag in tags_str.split():
        if tag.startswith("artist:"):
            artist = tag.split(":", 1)[1]
    return "unknown", artist


def _normalize_tag_token(raw: str | None) -> str:
    """Decode URL + HTML entities (e.g. ``girls&#039;_frontline`` → ``girls'_frontline``)."""
    if not raw:
        return ""
    name = html.unescape(unquote_plus(str(raw))).replace(" ", "_").strip()
    # Guard against double-encoded leftovers.
    if "&#" in name or "&amp;" in name.lower():
        name = html.unescape(name).replace(" ", "_").strip()
    return name


def _normalize_tag_string(tags: str | None) -> str:
    if not tags:
        return ""
    return " ".join(
        t for t in (_normalize_tag_token(tok) for tok in str(tags).split()) if t
    )


def _parse_tags_html_full(page_html: str) -> dict:
    typed: dict[str, list[str]] = {}
    for kind, body in _LI_RE.findall(page_html):
        for href_tag in _TAGS_HREF.findall(body):
            name = _normalize_tag_token(href_tag)
            if not name or name == "?":
                continue
            bucket = typed.setdefault(kind.lower(), [])
            if name not in bucket:
                bucket.append(name)
    all_tags: list[str] = []
    for names in typed.values():
        all_tags.extend(names)
    artists = list(typed.get("artist") or [])
    from bot.utils.artist_tags import is_valid_artist_tag, normalize_artist_tag

    artist = "unknown"
    if artists:
        artist = normalize_artist_tag(artists[0])
        if not is_valid_artist_tag(artist):
            artist = "unknown"
    characters = [
        tag
        for tag in (typed.get("character") or [])
        if tag.lower() not in _SKIP and not tag.startswith("(")
    ]
    return {
        "tags": " ".join(all_tags),
        "character_tag": characters[0] if characters else "unknown",
        "artist_tag": artist,
        "characters": characters,
        "artists": artists,
        "copyright": list(typed.get("copyright") or []),
        "general": list(typed.get("general") or []),
        "meta": list(typed.get("meta") or []),
    }


def _parse_tags_html(page_html: str) -> tuple[str, str, str]:
    parsed = _parse_tags_html_full(page_html)
    return parsed["tags"], parsed["character_tag"], parsed["artist_tag"]


def _abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return _clean_url(url)


def _clean_url(url: str) -> str:
    return url.replace("rule34.xxx//", "rule34.xxx/")


def _telegram_ok(url: str) -> bool:
    url = url.lower().split("?")[0]
    if any(x in url for x in (".swf", ".zip")):
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|gif|webp|mp4|webm)$", url))
