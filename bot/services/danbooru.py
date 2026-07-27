from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass

import httpx

import bot.core.config as _config
from bot.core.rate_limit import DANBOORU_RL
from bot.utils.booru_tags import BOORU_TAG_RE
from bot.utils.media_urls import url_ext

logger = logging.getLogger(__name__)


class _LiveCfg:
    """Always read the current Config — Settings reload rebinds bot.core.config.CFG."""

    def __getattr__(self, name: str):
        return getattr(_config.CFG, name)


CFG = _LiveCfg()

CHARACTER_TAG_RE = re.compile(r"^(\(|\)|\*|_|[a-z0-9_:-])+", re.I)
TAG_QUERY_RE = BOORU_TAG_RE
_METATAG_PREFIXES = ("order:", "rating:", "score:", "age:", "status:", "user:", "id:")

# Non-Gold Danbooru searches: every token counts, including negated tags.
DANBOORU_MAX_SEARCH_TAGS = 2


def danbooru_query_tag_count(tags: str) -> int:
    return sum(1 for part in (tags or "").split() if part)


def conjure_danbooru_query(tags: list[str]) -> str:
    """Build a Danbooru search for /conjure (plain tag join — no ``-webm``; see AGENTS.md)."""
    return " ".join(tags)


def _regular_tag_count(tags: str) -> int:
    n = 0
    for part in (tags or "").split():
        if not part or part.startswith("-") or any(part.startswith(p) for p in _METATAG_PREFIXES):
            continue
        n += 1
    return n


def _can_use_order_random(tags: str) -> bool:
    """Danbooru allows at most 2 tags; order:random counts as one."""
    return _regular_tag_count(tags) < 2


def _random_fetch_plans(tags: str, limit: int) -> list[tuple[str, dict]]:
    """Danbooru fetch strategies — order:random can time out on broad meta tags."""
    plans: list[tuple[str, dict]] = []
    if CFG.danbooru_api_key and _can_use_order_random(tags):
        plans.append(("/posts.json", {"tags": f"{tags} order:random", "limit": limit}))
    if CFG.danbooru_api_key:
        plans.append(("/posts/random.json", {"tags": tags}))
    page = random.randint(1, 200)
    plans.append(("/posts.json", {"tags": tags, "limit": limit, "page": page}))
    return plans


def is_danbooru_media_visible(raw: dict) -> bool:
    """True when the API exposes viewable media (md5 / file URLs) for this post."""
    if not raw or not raw.get("id"):
        return False
    if raw.get("md5"):
        return True
    if raw.get("file_url") or raw.get("large_file_url"):
        return True
    return False


@dataclass
class PostCountResult:
    count: int
    ok: bool


@dataclass
class DanbooruPost:
    post_id: int
    image_url: str
    character_tag: str
    artist_tag: str
    rating: str
    file_ext: str = "jpg"
    media_url: str = ""
    preview_url: str = ""
    image_width: int = 0
    image_height: int = 0
    is_animated: bool = False
    character_tag_candidates: tuple[str, ...] = ()


def _tag_matches_check_query(name: str, query: str) -> bool:
    """True when query is a full tag, prefix, or _-delimited segment — not a substring."""
    if name == query:
        return True
    if name.startswith(query):
        return True
    return query in name.split("_")


def _check_tag_sort_key(name: str, category: int, count: int, query: str) -> tuple:
    if name == query:
        tier = 2 if category == 3 else 0
    elif name.startswith(f"{query}_"):
        tier = 1
    elif name.startswith(query):
        tier = 2
    elif query in name.split("_"):
        tier = 3
    else:
        tier = 99
    cat_prio = {4: 0, 0: 1, 1: 2, 3: 3, 5: 4}.get(category, 5)
    return (tier, cat_prio, -count, name)


class DanbooruClient:
    BASE = "https://danbooru.donmai.us"
    UA = "ConjureFinder/1.0 (desktop; local tool)"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._tag_category_cache: dict[str, int | None] = {}
        self._tag_info_cache: dict[str, dict | None] = {}

    async def start(self) -> None:
        user = (CFG.danbooru_user or "").strip()
        key = (CFG.danbooru_api_key or "").strip()
        auth = (user, key) if user and key else None
        self._client = httpx.AsyncClient(
            base_url=self.BASE,
            headers={"User-Agent": self.UA},
            auth=auth,
            timeout=30.0,
            follow_redirects=True,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def random_post(
        self, tags: str, exclude_urls: set[str] | None = None, *, dedup: bool = True
    ) -> DanbooruPost | None:
        exclude_urls = exclude_urls or set()

        async def _fetch():
            assert self._client
            for attempt in range(5):
                post = await self._fetch_random_by_count(tags, exclude_urls)
                if post:
                    return post
            return None

        if not dedup:
            await DANBOORU_RL.acquire()
            return await _fetch()
        return await DANBOORU_RL.dedup(f"rand:{tags}", _fetch)

    async def _fetch_random_by_count(
        self,
        tags: str,
        exclude_urls: set[str],
        *,
        require_solo: bool = False,
        require_rating: str | None = None,
    ) -> DanbooruPost | None:
        assert self._client
        limit = 20
        tries = 3 if (require_solo or require_rating) else 1

        def _accept(raw: dict) -> bool:
            if require_solo and "solo" not in (raw.get("tag_string") or "").split():
                return False
            if require_rating and raw.get("rating") != require_rating:
                return False
            return True

        async def _pick(data: list) -> DanbooruPost | None:
            random.shuffle(data)
            for raw in data:
                if not _accept(raw):
                    continue
                if not is_danbooru_media_visible(raw):
                    continue
                post = _parse_post(raw)
                if not post:
                    continue
                urls = {post.image_url, post.media_url, post.preview_url}
                if any(u and u in exclude_urls for u in urls):
                    continue
                return await self._enrich_character_tag(post)
            return None

        for _ in range(tries):
            for path, params in _random_fetch_plans(tags, limit):
                r = await self._client.get(path, params=params)
                if r.status_code in (429, 421):
                    DANBOORU_RL.note_rate_limit()
                    await _sleep_rate(r)
                    break
                if r.status_code == 403:
                    logger.error("Danbooru 403 — check DANBOORU_USER and DANBOORU_API_KEY")
                    return None
                if r.status_code == 422:
                    logger.warning("Danbooru 422 tags=%r body=%s", tags, r.text[:200])
                    continue
                if r.status_code in (500, 502, 503):
                    logger.debug(
                        "Danbooru %s tags=%r path=%s — trying fallback",
                        r.status_code,
                        tags,
                        path,
                    )
                    continue
                if r.status_code != 200:
                    continue
                payload = r.json()
                if isinstance(payload, dict):
                    data = [payload] if payload.get("id") else []
                else:
                    data = payload or []
                if not data:
                    continue
                post = await _pick(data)
                if post:
                    return post
        return None

    async def fetch_by_tags(self, tags: str, exclude_urls: set[str] | None = None) -> DanbooruPost | None:
        return await self.random_post(tags, exclude_urls)

    async def fetch_post_by_id(self, post_id: int) -> DanbooruPost | None:
        assert self._client
        try:
            await DANBOORU_RL.acquire()
            r = await self._client.get(f"/posts/{int(post_id)}.json")
            if r.status_code != 200:
                return None
            post = _parse_post(r.json())
            return await self._enrich_character_tag(post) if post else None
        except Exception:
            logger.debug("fetch_post_by_id %s failed", post_id, exc_info=True)
            return None

    async def fetch_ugoira_preview_fallback(self, post_id: int) -> DanbooruPost | None:
        """Static preview for ugoira posts that cannot be stored as zip/webm."""
        assert self._client
        try:
            await DANBOORU_RL.acquire()
            r = await self._client.get(f"/posts/{int(post_id)}.json")
            if r.status_code != 200:
                return None
            post = _parse_ugoira_preview_fallback(r.json())
            return await self._enrich_character_tag(post) if post else None
        except Exception:
            logger.debug("fetch_ugoira_preview_fallback %s failed", post_id, exc_info=True)
            return None

    async def fetch_by_md5(self, md5: str) -> DanbooruPost | None:
        assert self._client
        md5 = md5.lower().strip()
        if not re.fullmatch(r"[a-f0-9]{32}", md5):
            return None

        async def _fetch():
            assert self._client
            r = await self._client.get(
                "/posts.json", params={"tags": f"md5:{md5}", "limit": 1}
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            raw = data[0] if isinstance(data, list) else data
            post = _parse_post(raw)
            return await self._enrich_character_tag(post) if post else None

        return await DANBOORU_RL.dedup(f"md5:{md5}", _fetch)

    async def count_posts_checked(self, tags: str) -> PostCountResult:
        assert self._client
        try:
            await DANBOORU_RL.acquire()
            r = await self._client.get("/counts/posts.json", params={"tags": tags})
            if r.status_code != 200:
                return PostCountResult(count=0, ok=False)
            data = r.json()
            count = int(data.get("counts", {}).get("posts", 0) or 0)
            return PostCountResult(count=count, ok=True)
        except Exception:
            logger.debug("danbooru count tags=%r failed", tags, exc_info=True)
            return PostCountResult(count=0, ok=False)

    async def count_posts(self, tags: str) -> int:
        return (await self.count_posts_checked(tags)).count

    async def count_accessible_posts(self, tags: str, *, limit: int) -> int:
        """Posts the bot can actually load — skips gold-locked rows without md5/URLs."""
        assert self._client
        cap = min(max(1, int(limit)), 200)
        try:
            await DANBOORU_RL.acquire()
            r = await self._client.get(
                "/posts.json", params={"tags": tags, "limit": cap}
            )
            if r.status_code != 200:
                return 0
            payload = r.json()
            if isinstance(payload, dict):
                items = [payload] if payload.get("id") else []
            else:
                items = payload or []
            return sum(1 for raw in items if is_danbooru_media_visible(raw))
        except Exception:
            logger.debug("danbooru accessible count tags=%r failed", tags, exc_info=True)
            return 0

    async def reshape(self, character_tag: str, rating: str, exclude: set[str]) -> DanbooruPost | None:
        tag = character_tag.replace(" ", "_")
        rating_map = {"G": "g", "S": "s", "Q": "q", "E": "e"}
        r = rating_map.get(rating.upper(), "g")
        query = f"solo {tag} rating:{r}"

        async def _fetch():
            assert self._client
            for _ in range(3):
                post = await self._fetch_random_by_count(
                    query, exclude, require_solo=True, require_rating=r
                )
                if post:
                    return post
            return None

        return await DANBOORU_RL.dedup(f"reshape:{query}", _fetch)

    async def reshape_multi(self, character_tag: str, rating: str, exclude: set[str]) -> DanbooruPost | None:
        tag = character_tag.replace(" ", "_")
        rating_map = {"G": "g", "S": "s", "Q": "q", "E": "e"}
        r = rating_map.get(rating.upper(), "g")
        query = f"{tag} -solo rating:{r}"

        async def _fetch():
            assert self._client
            for _ in range(3):
                post = await self._fetch_random_by_count(
                    query, exclude, require_solo=False, require_rating=r
                )
                if post:
                    return post
            return None

        return await DANBOORU_RL.dedup(f"reshape_multi:{query}", _fetch)

    async def by_artist(self, artist_tag: str, exclude: set[str]) -> DanbooruPost | None:
        tag = artist_tag.replace(" ", "_")
        return await self.random_post(tag, exclude, dedup=False)

    async def pick_popular_character_tag(self, candidates: list[str]) -> str:
        """Among character tags, prefer the one with the highest Danbooru post count."""
        if not candidates:
            return "unknown"
        if len(candidates) == 1:
            return candidates[0]
        best_tag = candidates[0]
        best_count = -1
        for tag in candidates:
            row = await self.tag_info(tag)
            count = int(row["count"]) if row else 0
            if count > best_count:
                best_count = count
                best_tag = tag
        return best_tag

    async def _enrich_character_tag(self, post: DanbooruPost) -> DanbooruPost:
        candidates = list(post.character_tag_candidates)
        if len(candidates) <= 1:
            return post
        tag = await self.pick_popular_character_tag(candidates)
        if tag == post.character_tag:
            return post
        from dataclasses import replace

        return replace(post, character_tag=tag)

    async def tag_info(self, name: str) -> dict | None:
        """Exact Danbooru tag metadata, or None if the name is not a real tag."""
        name = name.strip().lower().replace(" ", "_")
        if not name or not TAG_QUERY_RE.match(name):
            return None
        if name in self._tag_info_cache:
            return self._tag_info_cache[name]

        rows = await self.tag_info_many([name])
        return rows.get(name)

    async def tag_info_many(self, names: list[str]) -> dict[str, dict]:
        """Batch-fetch tag metadata (one HTTP call per ≤100 names).

        Uses ``search[name_normalize]`` so the browser-style “all tags at once”
        path does not burn one rate-limit slot per tag.
        """
        out: dict[str, dict] = {}
        pending: list[str] = []
        for raw in names:
            name = (raw or "").strip().lower().replace(" ", "_")
            if not name or not TAG_QUERY_RE.match(name):
                continue
            if name in self._tag_info_cache:
                if self._tag_info_cache[name] is not None:
                    out[name] = self._tag_info_cache[name]
                continue
            pending.append(name)
        # Dedupe while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for n in pending:
            if n not in seen:
                seen.add(n)
                ordered.append(n)

        chunk_size = 100
        for i in range(0, len(ordered), chunk_size):
            chunk = ordered[i : i + chunk_size]

            async def _fetch(chunk_names: list[str] = chunk) -> dict[str, dict]:
                assert self._client
                local: dict[str, dict] = {}
                try:
                    await DANBOORU_RL.acquire()
                    r = await self._client.get(
                        "/tags.json",
                        params={
                            "search[name_normalize]": ",".join(chunk_names),
                            "limit": min(len(chunk_names) + 10, 200),
                        },
                    )
                    if r.status_code != 200:
                        return local
                    for row in r.json() or []:
                        row_name = (row.get("name") or "").strip().lower()
                        if not row_name:
                            continue
                        info = {
                            "name": row.get("name") or row_name,
                            "category": int(row.get("category", 0)),
                            "count": int(row.get("post_count") or 0),
                        }
                        local[row_name] = info
                except Exception:
                    logger.debug(
                        "danbooru tag_info_many failed (%d names)",
                        len(chunk_names),
                        exc_info=True,
                    )
                return local

            batch = await DANBOORU_RL.dedup(
                f"taginfo_many:{','.join(chunk)}",
                _fetch,
            )
            for name in chunk:
                info = batch.get(name)
                self._tag_info_cache[name] = info
                if info is not None:
                    out[name] = info
        return out

    async def check_tags(self, query: str, *, limit: int = 8) -> list[dict]:
        """Autocomplete for /check — prefix and _-segment matches, no substring fuzz."""
        query = query.strip().lower().replace(" ", "_")
        if not query or not TAG_QUERY_RE.match(query):
            return []

        async def _fetch() -> list[dict]:
            assert self._client
            seen: dict[str, dict] = {}
            param_sets = [
                {"search[name_matches]": f"{query}*", "search[order]": "count"},
                {"search[name_matches]": f"*_{query}*", "search[order]": "count"},
                {"search[name]": query},
            ]
            for extra in param_sets:
                try:
                    await DANBOORU_RL.acquire()
                    r = await self._client.get(
                        "/tags.json",
                        params={"limit": min(limit * 4, 40), **extra},
                    )
                    if r.status_code != 200:
                        continue
                    for row in r.json() or []:
                        name = (row.get("name") or "").strip()
                        if not name or name in seen:
                            continue
                        if not _tag_matches_check_query(name, query):
                            continue
                        seen[name] = {
                            "name": name,
                            "category": int(row.get("category", 0)),
                            "count": int(row.get("post_count") or 0),
                        }
                except Exception:
                    logger.debug("danbooru check_tags %r failed", extra, exc_info=True)
            ranked = sorted(
                seen.values(),
                key=lambda x: _check_tag_sort_key(
                    x["name"], x["category"], x["count"], query
                ),
            )
            return ranked[:limit]

        return await DANBOORU_RL.dedup(f"check:{query}:{limit}", _fetch)

    async def tag_category(self, name: str) -> int | None:
        """0 general, 1 artist, 3 copyright, 4 character, 5 meta; None if unknown."""
        name = name.strip().lower().replace(" ", "_")
        if not name:
            return None
        if name in self._tag_category_cache:
            return self._tag_category_cache[name]

        row = await self.tag_info(name)
        cat = row["category"] if row else None
        self._tag_category_cache[name] = cat
        return cat

    async def suggest_tags(self, query: str, *, limit: int = 8) -> list[dict]:
        """Similar tag names via /tags.json search — autocomplete endpoint returns empty."""
        query = query.strip().lower().replace(" ", "_")
        if not query or not TAG_QUERY_RE.match(query):
            return []

        async def _fetch() -> list[dict]:
            assert self._client
            seen: dict[str, dict] = {}
            param_sets = [
                {"search[name_matches]": f"{query}*", "search[order]": "count"},
                {"search[name_matches]": f"*{query}*", "search[order]": "count"},
                {"search[name]": query},
            ]
            for extra in param_sets:
                try:
                    await DANBOORU_RL.acquire()
                    r = await self._client.get(
                        "/tags.json",
                        params={"limit": min(limit * 3, 20), **extra},
                    )
                    if r.status_code != 200:
                        continue
                    for row in r.json() or []:
                        name = (row.get("name") or "").strip()
                        if not name or name in seen:
                            continue
                        seen[name] = {
                            "name": name,
                            "category": int(row.get("category", 0)),
                            "count": int(row.get("post_count") or 0),
                        }
                except Exception:
                    logger.debug("danbooru suggest %r failed", extra, exc_info=True)
            ranked = sorted(
                seen.values(),
                key=lambda x: (
                    0 if x["name"] == query else (1 if x["name"].startswith(query) else 2),
                    -x["count"],
                    x["name"],
                ),
            )
            return ranked[:limit]

        return await DANBOORU_RL.dedup(f"suggest:{query}:{limit}", _fetch)


def _parse_post(raw: dict) -> DanbooruPost | None:
    file_ext = (raw.get("file_ext") or "").lower()
    if file_ext in ("swf", "webm"):
        return None
    file_url = _abs_url(raw.get("file_url"))
    large_url = _abs_url(raw.get("large_file_url"))
    if file_ext == "zip":
        return None
    preview_url = _abs_url(raw.get("preview_file_url"))
    if not preview_url or url_ext(preview_url) in ("gif", "mp4", "webm"):
        from bot.utils.media_urls import danbooru_sample_jpg_from_url

        derived = danbooru_sample_jpg_from_url(file_url or large_url)
        if derived:
            preview_url = derived
        elif large_url and url_ext(large_url) not in ("gif", "mp4", "webm"):
            preview_url = large_url
        else:
            preview_url = preview_url or ""
    if not file_url and not large_url:
        return None

    tags_general = raw.get("tag_string_general") or ""
    is_animated = file_ext in ("gif", "mp4", "webm") or "animated" in tags_general.split()

    if is_animated and file_ext in ("gif", "mp4", "webm"):
        media_url = file_url or large_url
        image_url = media_url
    else:
        media_url = file_url or large_url
        image_url = large_url or file_url or preview_url

    char_candidates = _character_tag_candidates(raw.get("tag_string_character", ""))
    char = _pick_character(raw.get("tag_string_character", ""))
    artist = _pick_artist(raw.get("tag_string_artist", ""))
    return DanbooruPost(
        post_id=raw["id"],
        image_url=image_url or "",
        character_tag=char or "unknown",
        character_tag_candidates=tuple(char_candidates),
        artist_tag=artist or "unknown",
        rating=raw.get("rating", "g"),
        file_ext=file_ext or "jpg",
        media_url=media_url or image_url,
        preview_url=preview_url or image_url,
        image_width=int(raw.get("image_width") or 0),
        image_height=int(raw.get("image_height") or 0),
        is_animated=is_animated,
    )


def _parse_ugoira_preview_fallback(raw: dict) -> DanbooruPost | None:
    """Last-resort static thumb for ugoira (zip) when the bundle was already awarded."""
    if (raw.get("file_ext") or "").lower() != "zip":
        return None
    preview_url = _abs_url(raw.get("preview_file_url"))
    preview_ext = url_ext(preview_url)
    if preview_ext not in ("jpg", "jpeg", "png", "webp"):
        return None
    char_candidates = _character_tag_candidates(raw.get("tag_string_character", ""))
    char = _pick_character(raw.get("tag_string_character", ""))
    artist = _pick_artist(raw.get("tag_string_artist", ""))
    return DanbooruPost(
        post_id=raw["id"],
        image_url=preview_url,
        character_tag=char or "unknown",
        character_tag_candidates=tuple(char_candidates),
        artist_tag=artist or "unknown",
        rating=raw.get("rating", "g"),
        file_ext=preview_ext,
        media_url=preview_url,
        preview_url=preview_url,
        image_width=int(raw.get("image_width") or 0),
        image_height=int(raw.get("image_height") or 0),
        is_animated=False,
    )


def _abs_url(url: str | None) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"https://danbooru.donmai.us{url}"


from bot.utils.formatting import format_character_name


def _pick_artist(tag_string: str) -> str:
    parts = tag_string.split()
    return parts[0] if parts else "unknown"


def _stored_artist_from_post(post: DanbooruPost) -> str:
    from bot.utils.artist_tags import is_valid_artist_tag, normalize_artist_tag

    tag = normalize_artist_tag(post.artist_tag)
    return tag if is_valid_artist_tag(tag) else "unknown"


def character_fields_from_post(post: DanbooruPost, **extra) -> dict:
    return {
        "post_id": post.post_id,
        "image_url": post.image_url,
        "file_url": post.media_url or post.image_url,
        "character_tag": post.character_tag,
        "artist_tag": _stored_artist_from_post(post),
        "rating": post.rating,
        "image_width": post.image_width,
        "image_height": post.image_height,
        "preview_url": post.preview_url,
        **extra,
    }


def _character_tag_candidates(tag_string: str) -> list[str]:
    return [
        tag
        for tag in (tag_string or "").split()
        if tag and not tag.startswith("(")
    ]


def _pick_character(tag_string: str) -> str:
    candidates = _character_tag_candidates(tag_string)
    if candidates:
        return candidates[0]  # keep raw danbooru tag for searches
    parts = (tag_string or "").split()
    return parts[0] if parts else "unknown"


def display_character_name(tag: str) -> str:
    return format_character_name(tag)


async def _sleep_rate(response: httpx.Response) -> None:
    import asyncio

    retry = 3
    header = response.headers.get("x-rate-limit")
    if header:
        try:
            import json

            data = json.loads(header)
            retry = max(2, int(data.get("reset_in", 3)))
        except Exception:
            pass
    await asyncio.sleep(retry)
