"""Combo-search persistence and URL builders."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sparse_tags.combo import (
    ComboState,
    add_recorded,
    build_combo_queries,
    load_combo,
    normalize_tag,
    posts_search_url,
    recorded_tags_text,
    remove_recorded,
    set_mode,
    set_recorded_enabled,
)


def _state(
    recorded: list[str],
    *,
    enabled: list[str] | None = None,
    mode: str = "danbooru",
    rating: str = "",
    r34_negatives: list[str] | None = None,
) -> ComboState:
    state = ComboState(
        mode=mode,  # type: ignore[arg-type]
        rating=rating,  # type: ignore[arg-type]
        r34_negatives=list(r34_negatives or []),
    )
    state.recorded = list(recorded)
    state.enabled = list(recorded if enabled is None else enabled)
    return state


class NormalizeTagTests(unittest.TestCase):
    def test_spaces_and_case(self) -> None:
        self.assertEqual(normalize_tag("  Blue Eyes  "), "blue_eyes")

    def test_strips_leading_minus(self) -> None:
        self.assertEqual(normalize_tag("-furry"), "furry")
        self.assertEqual(normalize_tag("--anthro"), "anthro")


class BuildComboQueriesTests(unittest.TestCase):
    def test_danbooru_pairs(self) -> None:
        state = _state(["solo", "1girl"], mode="danbooru", rating="")
        qs = build_combo_queries("new_tag", state)
        self.assertEqual([q for q, _ in qs], ["new_tag solo", "new_tag 1girl"])
        self.assertTrue(qs[0][1].startswith("https://danbooru.donmai.us/posts?tags="))

    def test_danbooru_rating(self) -> None:
        state = _state(["solo"], mode="danbooru", rating="g")
        qs = build_combo_queries("foo", state)
        self.assertEqual(qs[0][0], "foo solo rating:g")
        self.assertIn("rating%3Ag", qs[0][1])

    def test_rule34_negatives(self) -> None:
        state = _state(
            ["solo"],
            mode="rule34",
            r34_negatives=["furry", "anthro", "guro"],
        )
        qs = build_combo_queries("bar", state)
        self.assertEqual(qs[0][0], "bar solo -furry -anthro -guro")
        self.assertTrue(qs[0][1].startswith("https://rule34.xxx/"))

    def test_skips_self_pair(self) -> None:
        state = _state(["solo", "foo"], mode="danbooru")
        qs = build_combo_queries("foo", state)
        self.assertEqual([q for q, _ in qs], ["foo solo"])

    def test_skips_disabled(self) -> None:
        state = _state(["solo", "1girl"], enabled=["1girl"], mode="danbooru")
        qs = build_combo_queries("new_tag", state)
        self.assertEqual([q for q, _ in qs], ["new_tag 1girl"])

    def test_empty_input(self) -> None:
        state = _state(["solo"])
        self.assertEqual(build_combo_queries("  ", state), [])


class PostsUrlTests(unittest.TestCase):
    def test_quote(self) -> None:
        url = posts_search_url("danbooru", ["a", "b", "rating:g"])
        self.assertIn("a%20b%20rating%3Ag", url)


class PersistTests(unittest.TestCase):
    def test_add_remove_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse_tags_combo.json"
            with mock.patch("sparse_tags.combo.COMBO_PATH", path):
                state = ComboState()
                self.assertEqual(add_recorded(state, "Solo"), "solo")
                self.assertEqual(state.enabled, ["solo"])
                self.assertIsNone(add_recorded(state, "solo"))
                self.assertTrue(path.is_file())
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["pools"]["danbooru"]["enabled"], ["solo"])
                self.assertEqual(payload["pools"]["rule34"]["recorded"], [])
                self.assertTrue(remove_recorded(state, "solo"))
                self.assertEqual(state.recorded, [])
                self.assertEqual(state.enabled, [])

    def test_new_tag_auto_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse_tags_combo.json"
            with mock.patch("sparse_tags.combo.COMBO_PATH", path):
                state = ComboState()
                add_recorded(state, "a")
                add_recorded(state, "b")
                set_recorded_enabled(state, "a", False)
                self.assertEqual(state.enabled, ["b"])
                add_recorded(state, "c")
                self.assertEqual(state.enabled, ["b", "c"])

    def test_legacy_load_goes_to_danbooru_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse_tags_combo.json"
            path.write_text(
                json.dumps({"recorded": ["solo", "1girl"], "mode": "danbooru"}),
                encoding="utf-8",
            )
            with mock.patch("sparse_tags.combo.COMBO_PATH", path):
                state = load_combo()
                self.assertEqual(state.recorded, ["solo", "1girl"])
                self.assertEqual(state.enabled, ["solo", "1girl"])
                set_mode(state, "rule34")
                self.assertEqual(state.recorded, [])
                self.assertEqual(state.enabled, [])

    def test_separate_pools_per_site(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sparse_tags_combo.json"
            with mock.patch("sparse_tags.combo.COMBO_PATH", path):
                state = ComboState()
                add_recorded(state, "painterly")
                set_mode(state, "rule34")
                self.assertEqual(state.recorded, [])
                add_recorded(state, "1girls")
                self.assertEqual(state.recorded, ["1girls"])
                set_mode(state, "danbooru")
                self.assertEqual(state.recorded, ["painterly"])
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    payload["pools"]["danbooru"]["recorded"], ["painterly"]
                )
                self.assertEqual(payload["pools"]["rule34"]["recorded"], ["1girls"])

    def test_recorded_tags_text(self) -> None:
        state = _state(["solo", "1girl"])
        self.assertEqual(recorded_tags_text(state), "solo\n1girl")


if __name__ == "__main__":
    unittest.main()
