"""Fetch sparse Danbooru / Rule34 tags via their tag APIs."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx

from bot.core.rate_limit import DANBOORU_RL
from bot.services.rule34 import API as R34_API
from bot.services.rule34 import UA as R34_UA
from bot.services.rule34 import _parse_tag_index_payload

Source = Literal["danbooru", "rule34"]

DANBOORU_BASE = "https://danbooru.donmai.us"
R34_SITE = "https://rule34.xxx"
UA = "SparseTagBrowser/1.0 (desktop; personal tool)"
# Danbooru caps tag list pages; 100 is safe for non-Gold.
PAGE_LIMIT = 100
# Hard ceiling so we don't spam the API if someone sets a huge batch.
MAX_FETCH_PAGES = 40
# Rule34 order=count pid space (limit=100): empty tags, then 1-post, …
R34_PID_LO = 0
R34_PID_HI = 17_000
# Approximate first pid where page counts reach N (from live probes; limit=100).
# Used to skip the huge empty-tag prefix without a slow binary search.
_R34_COUNT_PID: tuple[tuple[int, int], ...] = (
    (0, 0),
    (1, 400),
    (2, 8_000),
    (3, 9_000),
    (4, 10_000),
    (6, 11_000),
    (10, 12_000),
    (15, 12_500),
    (25, 13_200),
    (33, 14_000),
    (90, 15_000),
    (500, 15_500),
    (2400, 16_000),
)


@dataclass(frozen=True)
class SparseTag:
    name: str
    post_count: int
    category: int
    source: Source = "danbooru"
    is_deprecated: bool = False

    @property
    def posts_url(self) -> str:
        if self.source == "rule34":
            return (
                f"{R34_SITE}/index.php?page=post&s=list"
                f"&tags={quote(self.name, safe='')}"
            )
        return f"{DANBOORU_BASE}/posts?tags={quote(self.name, safe='')}"

    @property
    def tag_url(self) -> str:
        if self.source == "rule34":
            return (
                f"{R34_SITE}/index.php?page=wiki&s=list"
                f"&search={quote(self.name, safe='')}"
            )
        return (
            f"{DANBOORU_BASE}/tags?search%5Bname_matches%5D="
            f"{quote(self.name, safe='')}"
        )


@dataclass
class FetchRequest:
    source: Source = "danbooru"
    min_count: int = 1
    max_count: int = 25
    category: int = 0  # general
    batch_size: int = 80
    hide_empty: bool = True
    exclude_deprecated: bool = True
    exclude_cosplay: bool = True
    seed: int | None = None


def _danbooru_auth() -> tuple[str, str] | None:
    import bot.core.config as cfg_mod

    user = (cfg_mod.CFG.danbooru_user or "").strip()
    key = (cfg_mod.CFG.danbooru_api_key or "").strip()
    if user and key:
        return (user, key)
    return None


def _rule34_auth() -> dict[str, str] | None:
    import bot.core.config as cfg_mod

    key = (cfg_mod.CFG.rule34_api_key or "").strip()
    uid = str(cfg_mod.CFG.rule34_user_id or "").strip()
    if key and uid:
        return {"api_key": key, "user_id": uid}
    return None


def has_danbooru_auth() -> bool:
    return _danbooru_auth() is not None


def has_rule34_auth() -> bool:
    return _rule34_auth() is not None


def has_auth_for(source: Source) -> bool:
    if source == "rule34":
        return has_rule34_auth()
    return has_danbooru_auth()


def _validate_req(req: FetchRequest) -> None:
    if req.min_count < 1:
        raise ValueError("min_count must be >= 1")
    if req.max_count < req.min_count:
        raise ValueError("max_count must be >= min_count")
    if req.batch_size < 1:
        raise ValueError("batch_size must be >= 1")


async def fetch_sparse_tags(
    req: FetchRequest,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SparseTag]:
    """Pull a shuffled batch of tags with post_count in [min_count, max_count]."""
    _validate_req(req)
    if req.source == "rule34":
        return await _fetch_rule34(req, progress=progress, cancel_check=cancel_check)
    return await _fetch_danbooru(req, progress=progress, cancel_check=cancel_check)


async def _fetch_danbooru(
    req: FetchRequest,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SparseTag]:
    auth = _danbooru_auth()
    if not auth:
        raise ValueError(
            "Danbooru API keys missing — open Conjure Finder → Settings…, "
            "save username + API key, then retry."
        )

    rng = random.Random(req.seed)
    pages_needed = min(
        MAX_FETCH_PAGES,
        max(1, (req.batch_size + PAGE_LIMIT - 1) // PAGE_LIMIT),
    )
    candidate_pages = list(range(1, max(pages_needed * 8, 40)))
    rng.shuffle(candidate_pages)
    pages_to_try = candidate_pages[: pages_needed * 3]

    params_base: dict[str, str | int] = {
        "limit": PAGE_LIMIT,
        "search[category]": req.category,
        "search[hide_empty]": "yes" if req.hide_empty else "no",
        "search[post_count]": f"{req.min_count}..{req.max_count}",
    }
    if req.exclude_deprecated:
        params_base["search[is_deprecated]"] = "false"

    collected: dict[str, SparseTag] = {}

    async with httpx.AsyncClient(
        base_url=DANBOORU_BASE,
        headers={"User-Agent": UA},
        auth=auth,
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for i, page in enumerate(pages_to_try):
            if cancel_check and cancel_check():
                break
            if len(collected) >= req.batch_size * 2:
                break
            if progress:
                progress(
                    f"Danbooru page {page}… "
                    f"({len(collected)} tags so far, need ~{req.batch_size})"
                )
            params = {**params_base, "page": page}
            await DANBOORU_RL.acquire()
            try:
                r = await client.get("/tags.json", params=params)
            except httpx.HTTPError as e:
                raise ValueError(f"Danbooru request failed: {e}") from e
            if r.status_code == 401:
                raise ValueError(
                    "Danbooru 401 — check username (login name, not email) and API key."
                )
            if r.status_code == 403:
                raise ValueError("Danbooru 403 — check username/API key in Settings…")
            if r.status_code == 429:
                DANBOORU_RL.note_rate_limit()
                await asyncio.sleep(2.0)
                continue
            if r.status_code >= 400:
                raise ValueError(f"Danbooru HTTP {r.status_code}: {r.text[:200]}")
            items = r.json()
            if not isinstance(items, list) or not items:
                continue
            for raw in items:
                tag = _tag_from_danbooru(raw, req)
                if tag:
                    collected[tag.name] = tag
            if len(collected) >= req.batch_size and i + 1 >= pages_needed:
                break

    tags = list(collected.values())
    rng.shuffle(tags)
    return tags[: req.batch_size]


def _tag_from_danbooru(raw: dict, req: FetchRequest) -> SparseTag | None:
    name = (raw.get("name") or "").strip()
    if not name:
        return None
    if req.exclude_cosplay and "(cosplay)" in name:
        return None
    count = int(raw.get("post_count") or 0)
    if count < req.min_count or count > req.max_count:
        return None
    return SparseTag(
        name=name,
        post_count=count,
        category=int(raw.get("category") or 0),
        source="danbooru",
        is_deprecated=bool(raw.get("is_deprecated")),
    )


def _r34_pid_for_count(target: int) -> int:
    """Approximate order=count pid where tags of ``target`` posts begin."""
    pid = R34_PID_LO
    for count, p in _R34_COUNT_PID:
        if count <= target:
            pid = p
        else:
            break
    return max(R34_PID_LO, min(R34_PID_HI, pid))


def _r34_pid_bounds(req: FetchRequest) -> tuple[int, int]:
    """Pid window covering [min_count, max_count] on order=count listings."""
    first = _r34_pid_for_count(req.min_count)
    # Pad past the max-count band so random samples still hit the upper edge.
    last = min(R34_PID_HI, _r34_pid_for_count(req.max_count) + 800)
    if last < first:
        last = first
    return first, last


async def _fetch_rule34(
    req: FetchRequest,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SparseTag]:
    auth = _rule34_auth()
    if not auth:
        raise ValueError(
            "Rule34 API keys missing — open Conjure Finder → Settings…, "
            "save API key + user id, then retry."
        )

    rng = random.Random(req.seed)
    collected: dict[str, SparseTag] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": R34_UA},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        first_pid, last_pid = _r34_pid_bounds(req)
        if progress:
            progress(
                f"Rule34: sampling pids {first_pid}–{last_pid} "
                f"(counts {req.min_count}–{req.max_count})…"
            )

        pages_needed = min(
            MAX_FETCH_PAGES,
            max(1, (req.batch_size + PAGE_LIMIT - 1) // PAGE_LIMIT),
        )
        # Oversample — many rows are non-general / out of range.
        tries = min(pages_needed * 4, max(12, (last_pid - first_pid) // 50 + 1))
        pids = list(range(first_pid, last_pid + 1))
        if not pids:
            pids = [first_pid]
        rng.shuffle(pids)
        pids = pids[:tries]

        for i, pid in enumerate(pids):
            if cancel_check and cancel_check():
                break
            if len(collected) >= req.batch_size * 2:
                break
            if progress:
                progress(
                    f"Rule34 pid {pid}… "
                    f"({len(collected)} tags so far, need ~{req.batch_size})"
                )
            r = await client.get(
                R34_API,
                params={
                    **auth,
                    "page": "dapi",
                    "s": "tag",
                    "q": "index",
                    "json": "1",
                    "order": "count",
                    "limit": str(PAGE_LIMIT),
                    "pid": str(pid),
                },
            )
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(1.2)
                continue
            if r.status_code != 200 or not r.content:
                continue
            for raw in _parse_tag_index_payload(r.content):
                tag = _tag_from_rule34(raw, req)
                if tag:
                    collected[tag.name] = tag
            if len(collected) >= req.batch_size and i + 1 >= pages_needed:
                break

    tags = list(collected.values())
    rng.shuffle(tags)
    return tags[: req.batch_size]


def _tag_from_rule34(raw: dict, req: FetchRequest) -> SparseTag | None:
    name = (raw.get("name") or "").strip().lower().replace(" ", "_")
    if not name:
        return None
    if req.exclude_cosplay and "(cosplay)" in name:
        return None
    try:
        category = int(raw.get("type", raw.get("category", 0)))
    except (TypeError, ValueError):
        category = 0
    if category != req.category:
        return None
    try:
        count = int(raw.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    if count < req.min_count or count > req.max_count:
        return None
    return SparseTag(
        name=name,
        post_count=count,
        category=category,
        source="rule34",
        is_deprecated=False,
    )


def fetch_sparse_tags_sync(
    req: FetchRequest,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SparseTag]:
    return asyncio.run(
        fetch_sparse_tags(req, progress=progress, cancel_check=cancel_check)
    )
