"""Tkinter UI: randomized sparse Danbooru / Rule34 tags; click opens in browser."""

from __future__ import annotations

import random
import sys
import threading
import tkinter as tk
import webbrowser
from typing import Any
from tkinter import messagebox, simpledialog, ttk

from sparse_tags import __version__
from sparse_tags.favourites import (
    FavEntry,
    fav_tags,
    get_note,
    is_favourite,
    load_favourites,
    set_note,
    sorted_fav_entries,
    toggle_favourite,
)
from sparse_tags.fetch import (
    FetchRequest,
    Source,
    SparseTag,
    fetch_sparse_tags_sync,
    has_auth_for,
)
from sparse_tags.combo_ui import ComboSearchPanel
from sparse_tags.history import load_seen, mark_opened
from sparse_tags.prefs import load_prefs, save_prefs
from sparse_tags.theme import (
    RegionMousewheel,
    apply_app_theme,
    schedule_theme_refresh,
    surface_for,
    themed_spinbox,
    zebra,
)


class SparseTagBrowser(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Sparse Tag Browser  v{__version__}")
        self.minsize(560, 520)
        apply_app_theme(self)

        self._prefs = load_prefs()
        try:
            self.geometry(str(self._prefs.get("geometry") or "720x680"))
        except tk.TclError:
            self.geometry("720x680")

        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._tags: list[SparseTag] = []
        self._seen = load_seen()
        self._selected: set[str] = set()
        self._select_vars: dict[str, tk.BooleanVar] = {}
        self._fav_btns: dict[str, ttk.Button] = {}
        self._name_lbls: dict[str, tk.Label] = {}
        self._row_by_name: dict[str, tk.Frame] = {}
        self._favs = load_favourites()
        self._fav_window: FavouritesWindow | None = None
        self._row_widgets: list[tk.Widget] = []
        self._walk_index = 0
        self._save_job: str | None = None
        self._hint_lbl: ttk.Label | None = None
        self._update_busy = False
        self._combo: ComboSearchPanel | None = None

        self._build()
        apply_app_theme(self)
        schedule_theme_refresh(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._update_auth_hint)
        from sparse_tags.updater import load_update_config

        if load_update_config().check_updates:
            self.after(1500, lambda: self.check_updates(silent=True))

    def walk_size(self) -> int:
        try:
            return max(1, min(50, int(self.walk_size_var.get())))
        except (tk.TclError, TypeError, ValueError):
            return 5

    def _build(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)
        sparse_tab = ttk.Frame(nb, padding=12)
        combo_tab = ttk.Frame(nb)
        nb.add(sparse_tab, text="Sparse tags")
        nb.add(combo_tab, text="Combo search")
        self._notebook = nb
        self._build_sparse(sparse_tab)
        self._combo = ComboSearchPanel(combo_tab, host=self)
        self._combo.pack(fill=tk.BOTH, expand=True)

    def _build_sparse(self, root: ttk.Frame) -> None:
        pad = {"padx": 10, "pady": 4}
        p = self._prefs

        opts = ttk.LabelFrame(root, text="Pool filter", padding=8)
        opts.pack(fill=tk.X, **pad)

        row0 = ttk.Frame(opts)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Source").pack(side=tk.LEFT)
        self.source_var = tk.StringVar(value=str(p["source"]))
        ttk.Radiobutton(
            row0,
            text="Danbooru",
            value="danbooru",
            variable=self.source_var,
            command=self._on_source_change,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(
            row0,
            text="Rule34",
            value="rule34",
            variable=self.source_var,
            command=self._on_source_change,
        ).pack(side=tk.LEFT, padx=(8, 0))
        # Load / shuffle / cancel on the filter row — away from walk controls.
        self.cancel_btn = ttk.Button(
            row0, text="Cancel", command=self.cancel_load, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.RIGHT)
        self.shuffle_btn = ttk.Button(
            row0, text="Shuffle", command=self.shuffle_list, state=tk.DISABLED
        )
        self.shuffle_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.load_btn = ttk.Button(row0, text="Load random batch", command=self.start_load)
        self.load_btn.pack(side=tk.RIGHT, padx=(0, 8))

        row1 = ttk.Frame(opts)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Min posts").pack(side=tk.LEFT)
        self.min_var = tk.IntVar(value=int(p["min_count"]))
        themed_spinbox(row1, from_=1, to=500, width=6, textvariable=self.min_var).pack(
            side=tk.LEFT, padx=(6, 16)
        )
        ttk.Label(row1, text="Max posts").pack(side=tk.LEFT)
        self.max_var = tk.IntVar(value=int(p["max_count"]))
        themed_spinbox(row1, from_=1, to=500, width=6, textvariable=self.max_var).pack(
            side=tk.LEFT, padx=(6, 16)
        )
        ttk.Label(row1, text="Load size").pack(side=tk.LEFT)
        self.batch_var = tk.IntVar(value=int(p["batch_size"]))
        themed_spinbox(row1, from_=10, to=500, width=6, textvariable=self.batch_var).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        row2 = ttk.Frame(opts)
        row2.pack(fill=tk.X, pady=2)
        self.no_cosplay_var = tk.BooleanVar(value=bool(p["exclude_cosplay"]))
        ttk.Checkbutton(
            row2, text="Exclude (cosplay)", variable=self.no_cosplay_var
        ).pack(side=tk.LEFT)
        self.no_deprecated_var = tk.BooleanVar(value=bool(p["exclude_deprecated"]))
        self.deprecated_cb = ttk.Checkbutton(
            row2, text="Exclude deprecated", variable=self.no_deprecated_var
        )
        self.deprecated_cb.pack(side=tk.LEFT, padx=(12, 0))
        self.favs_btn = ttk.Button(row2, text="Favourites…", command=self.open_favourites)
        self.favs_btn.pack(side=tk.RIGHT)
        self.update_btn = ttk.Button(
            row2, text="Check for updates", command=lambda: self.check_updates(silent=False)
        )
        self.update_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.clear_seen_btn = ttk.Button(
            row2, text="Clear opened history", command=self.clear_opened_history
        )
        self.clear_seen_btn.pack(side=tk.RIGHT, padx=(0, 8))

        # Walk / open controls — separate from Load.
        walk = ttk.LabelFrame(root, text="Browse walk", padding=8)
        walk.pack(fill=tk.X, **pad)
        ttk.Label(walk, text="Open next").pack(side=tk.LEFT)
        self.walk_size_var = tk.IntVar(value=int(p.get("walk_size") or 5))
        themed_spinbox(
            walk,
            from_=1,
            to=50,
            width=4,
            textvariable=self.walk_size_var,
            command=self._on_walk_size,
        ).pack(side=tk.LEFT, padx=(6, 4))
        ttk.Label(walk, text="tags").pack(side=tk.LEFT)
        self.open_next_btn = ttk.Button(
            walk, text="Open next batch", command=self.open_next_batch, state=tk.DISABLED
        )
        self.open_next_btn.pack(side=tk.LEFT, padx=(12, 0))
        self.reset_walk_btn = ttk.Button(
            walk, text="Reset walk", command=self.reset_walk, state=tk.DISABLED
        )
        self.reset_walk_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.walk_var = tk.StringVar(value="Walk: —")
        ttk.Label(walk, textvariable=self.walk_var).pack(side=tk.LEFT, padx=(12, 0))
        self.open_sel_btn = ttk.Button(
            walk, text="Open selected", command=self.open_selected, state=tk.DISABLED
        )
        self.open_sel_btn.pack(side=tk.RIGHT)
        self.clear_sel_btn = ttk.Button(
            walk, text="Clear selection", command=self.clear_selection, state=tk.DISABLED
        )
        self.clear_sel_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self._hint_lbl = ttk.Label(
            root,
            text=(
                "Check to multi-select · ✓ = opened in browser · "
                "new loads skip only those · keys: conjure_finder.env"
            ),
        )
        self._hint_lbl.pack(anchor=tk.W, padx=10)
        list_frame = ttk.Frame(root)
        list_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self._list_frame = list_frame

        c = surface_for(self)
        self._canvas = tk.Canvas(
            list_frame, highlightthickness=0, bg=c["canvas"]
        )
        self._rows = tk.Frame(self._canvas, bg=c["canvas"])
        self._rows.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas_window = self._canvas.create_window((0, 0), window=self._rows, anchor=tk.NW)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        RegionMousewheel.register(self, self._canvas, list_frame)

        self.status_var = tk.StringVar(
            value="Pick Danbooru or Rule34, then Load. API keys from conjure_finder.env (shared with Conjure Finder)."
        )
        ttk.Label(root, textvariable=self.status_var, wraplength=680).pack(
            fill=tk.X, anchor=tk.W, **pad
        )

        for var in (
            self.source_var,
            self.min_var,
            self.max_var,
            self.batch_var,
            self.walk_size_var,
            self.no_cosplay_var,
            self.no_deprecated_var,
        ):
            var.trace_add("write", lambda *_a: self._schedule_save_prefs())

        self._on_source_change()
        self._on_walk_size()
        self._refresh_list(reset_scroll=False)

    def _on_walk_size(self) -> None:
        n = self.walk_size()
        if self._hint_lbl is not None:
            self._hint_lbl.configure(
                text=(
                    f"Open next {n} walks the list · check to multi-select · "
                    "count opens one · ★ favourites · keys: conjure_finder.env"
                )
            )
        self._update_walk_ui()
        self._schedule_save_prefs()

    def _on_close(self) -> None:
        self._persist_prefs()
        if self._combo is not None:
            self._combo.persist()
        self.destroy()

    def _schedule_save_prefs(self) -> None:
        if self._save_job is not None:
            try:
                self.after_cancel(self._save_job)
            except tk.TclError:
                pass
        self._save_job = self.after(400, self._persist_prefs)

    def _persist_prefs(self) -> None:
        self._save_job = None
        try:
            min_c = int(self.min_var.get())
            max_c = int(self.max_var.get())
            batch = int(self.batch_var.get())
            walk = int(self.walk_size_var.get())
        except (tk.TclError, TypeError, ValueError):
            return
        try:
            geometry = self.geometry()
        except tk.TclError:
            geometry = str(self._prefs.get("geometry") or "720x680")
        fav_geo = str(self._prefs.get("fav_geometry") or "560x480")
        fav_sort = str(self._prefs.get("fav_sort") or "favourited")
        if self._fav_window and self._fav_window.winfo_exists():
            try:
                fav_geo = self._fav_window.geometry()
            except tk.TclError:
                pass
            fav_sort = self._fav_window.fav_sort()
        save_prefs(
            {
                "source": self._current_source(),
                "min_count": min_c,
                "max_count": max_c,
                "batch_size": batch,
                "walk_size": walk,
                "exclude_cosplay": bool(self.no_cosplay_var.get()),
                "exclude_deprecated": bool(self.no_deprecated_var.get()),
                "geometry": geometry,
                "fav_geometry": fav_geo,
                "fav_sort": fav_sort,
            }
        )
        self._prefs["geometry"] = geometry
        self._prefs["fav_geometry"] = fav_geo
        self._prefs["fav_sort"] = fav_sort

    def clear_opened_history(self) -> None:
        source = self._current_source()
        label = "Rule34" if source == "rule34" else "Danbooru"
        n = len(self._seen.get(source, set()))
        if n == 0:
            messagebox.showinfo(
                "Sparse Tag Browser",
                f"No opened {label} tags in history yet.",
            )
            return
        if not messagebox.askyesno(
            "Sparse Tag Browser",
            f"Clear {n} opened {label} tag(s) from history?\n\n"
            "They can appear in new loads again.",
        ):
            return
        self._seen[source] = set()
        from sparse_tags.history import save_seen

        save_seen(self._seen)
        self._walk_index = 0
        self._refresh_list()
        self.status_var.set(f"Cleared opened history for {label}.")

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _current_source(self) -> Source:
        raw = (self.source_var.get() or "danbooru").strip().lower()
        return "rule34" if raw == "rule34" else "danbooru"

    def _on_source_change(self) -> None:
        src = self._current_source()
        state = tk.NORMAL if src == "danbooru" else tk.DISABLED
        self.deprecated_cb.configure(state=state)
        self._schedule_save_prefs()
        self._update_auth_hint()

    def _update_auth_hint(self) -> None:
        from sparse_tags.bootstrap import LOADED_KEYS_PATH, ROOT

        src = self._current_source()
        if has_auth_for(src):
            label = "Rule34" if src == "rule34" else "Danbooru"
            where = str(LOADED_KEYS_PATH) if LOADED_KEYS_PATH else str(ROOT)
            self.status_var.set(f"{label} keys OK ({where}). Set range, then Load.")
            return
        self.status_var.set(
            f"No keys in {ROOT / 'conjure_finder.env'} — "
            "put this exe in the same folder as Conjure Finder.exe "
            "and its conjure_finder.env (Settings…)."
        )

    def _seen_for(self, source: Source | None = None) -> set[str]:
        src = source or (
            self._tags[0].source if self._tags else self._current_source()
        )
        return self._seen.setdefault(src, set())

    def _visible_tags(self) -> list[SparseTag]:
        # Full current load stays on screen (opened ones keep a ✓).
        # New loads skip only tags whose posts were actually opened.
        return list(self._tags)

    def _clear_rows(self) -> None:
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()
        self._fav_btns.clear()
        self._name_lbls.clear()
        self._row_by_name.clear()
        self._select_vars.clear()

    def _refresh_list(self, *, reset_scroll: bool = True) -> None:
        visible_names = {t.name for t in self._visible_tags()}
        self._selected &= visible_names
        if self._walk_index > len(self._visible_tags()):
            self._walk_index = 0
        self._clear_rows()
        c = surface_for(self)
        try:
            self._rows.configure(bg=c["canvas"])
            self._canvas.configure(bg=c["canvas"])
        except tk.TclError:
            pass
        tags = self._visible_tags()
        if not tags:
            empty = tk.Label(
                self._rows,
                text="No tags loaded yet — set the pool filter, then Load random batch.",
                bg=c["canvas"],
                fg=c["muted"],
                anchor=tk.W,
                justify=tk.LEFT,
                font=("Segoe UI", 10),
            )
            empty._sparse_row_tint = True  # type: ignore[attr-defined]
            empty.pack(anchor=tk.W, padx=10, pady=16)
            self._row_widgets.append(empty)
        else:
            for i, tag in enumerate(tags):
                self._add_tag_row(self._rows, tag, index=i)
        self._update_status_line()
        self.shuffle_btn.configure(state=tk.NORMAL if self._tags else tk.DISABLED)
        self._update_selection_buttons()
        self._update_walk_ui()
        if reset_scroll:
            self._canvas.yview_moveto(0)

    def _update_status_line(self) -> None:
        n = len(self._visible_tags())
        src = self._tags[0].source if self._tags else self._current_source()
        seen = len(self._seen_for(src))
        sel = len(self._selected)
        self.status_var.set(
            f"{src}: showing {n} tag(s)"
            + (f" · {sel} selected" if sel else "")
            + (f" · {seen} opened total" if seen else "")
            + f" · {self._fav_count(src)} favourited"
        )

    def _update_selection_buttons(self) -> None:
        state = tk.NORMAL if self._selected else tk.DISABLED
        self.open_sel_btn.configure(state=state)
        self.clear_sel_btn.configure(state=state)

    def _update_walk_ui(self) -> None:
        total = len(self._visible_tags())
        ws = self.walk_size()
        has = total > 0
        self.open_next_btn.configure(state=tk.NORMAL if has else tk.DISABLED)
        self.reset_walk_btn.configure(state=tk.NORMAL if has else tk.DISABLED)
        if not has:
            self.walk_var.set("Walk: —")
            return
        at = min(self._walk_index, total)
        remaining = max(0, total - at)
        if remaining == 0:
            self.walk_var.set(f"Walk: done ({total}/{total})")
            self.open_next_btn.configure(state=tk.DISABLED)
        else:
            nxt = min(ws, remaining)
            self.walk_var.set(f"Walk: next {nxt} · at {at}/{total}")

    def _on_select_toggle(self, tag: SparseTag, var: tk.BooleanVar) -> None:
        if var.get():
            self._selected.add(tag.name)
        else:
            self._selected.discard(tag.name)
        self._update_selection_buttons()
        self._update_status_line()

    def _fav_count(self, source: Source) -> int:
        return len(self._favs.get(source, []))

    def _add_tag_row(self, parent: tk.Frame, tag: SparseTag, *, index: int) -> None:
        c = surface_for(self)
        bg = zebra(index, self)
        row = tk.Frame(parent, bg=bg, highlightthickness=0)
        row.pack(fill=tk.X, pady=0, padx=0, ipady=2)
        self._row_widgets.append(row)
        self._row_by_name[tag.name] = row

        var = tk.BooleanVar(value=tag.name in self._selected)
        self._select_vars[tag.name] = var
        cb = tk.Checkbutton(
            row,
            variable=var,
            command=lambda t=tag, v=var: self._on_select_toggle(t, v),
            bg=bg,
            fg=c["fg"],
            activebackground=bg,
            activeforeground=c["fg"],
            selectcolor=c["entry"],
            highlightthickness=0,
            bd=0,
        )
        cb._sparse_row_tint = True  # type: ignore[attr-defined]
        cb.pack(side=tk.LEFT, padx=(4, 0))

        count_btn = tk.Button(
            row,
            text=str(tag.post_count),
            width=5,
            command=lambda t=tag: self.open_tag_posts(t),
            relief=tk.FLAT,
            bg=c["button"],
            fg=c["fg"],
            activebackground=c["button_active"],
            activeforeground=c["fg"],
            bd=0,
            highlightthickness=0,
        )
        count_btn._sparse_custom_btn = True  # type: ignore[attr-defined]
        count_btn.pack(side=tk.LEFT, padx=(2, 0))

        mark = "  ✓" if tag.name in self._seen_for(tag.source) else ""
        name_lbl = tk.Label(
            row,
            text=f"{tag.name}{mark}",
            font=("Consolas", 11),
            bg=bg,
            fg=c["fg"],
            anchor=tk.W,
        )
        name_lbl._sparse_row_tint = True  # type: ignore[attr-defined]
        name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4))
        name_lbl.bind("<Button-1>", lambda _e, t=tag, v=var: self._toggle_row_select(t, v))
        name_lbl.bind("<Button-3>", lambda e, t=tag: self._popup_tag_menu(e, t))
        self._name_lbls[tag.name] = name_lbl

        fav = is_favourite(self._favs, tag.source, tag.name)
        fav_btn = ttk.Button(
            row,
            text="★" if fav else "☆",
            width=3,
            command=lambda t=tag: self._toggle_fav(t),
        )
        fav_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self._fav_btns[tag.name] = fav_btn

    def _toggle_row_select(self, tag: SparseTag, var: tk.BooleanVar) -> None:
        var.set(not var.get())
        self._on_select_toggle(tag, var)

    def _popup_tag_menu(self, event: tk.Event, tag: SparseTag) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open posts", command=lambda: self.open_tag_posts(tag))
        menu.add_command(
            label="Open tag / wiki", command=lambda: webbrowser.open(tag.tag_url)
        )
        menu.add_command(
            label="Copy tag name",
            command=lambda: self._copy_name(tag.name),
        )
        selected = tag.name in self._selected
        menu.add_command(
            label="Deselect" if selected else "Select",
            command=lambda: self._menu_toggle_select(tag),
        )
        fav = is_favourite(self._favs, tag.source, tag.name)
        menu.add_command(
            label="Unfavourite" if fav else "Favourite",
            command=lambda: self._toggle_fav(tag),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _menu_toggle_select(self, tag: SparseTag) -> None:
        var = self._select_vars.get(tag.name)
        if var is None:
            if tag.name in self._selected:
                self._selected.discard(tag.name)
            else:
                self._selected.add(tag.name)
            self._update_selection_buttons()
            return
        var.set(not var.get())
        self._on_select_toggle(tag, var)

    def _copy_name(self, name: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(name)
        self.status_var.set(f"Copied: {name}")

    def _selected_tags(self) -> list[SparseTag]:
        return [t for t in self._visible_tags() if t.name in self._selected]

    def clear_selection(self) -> None:
        self._selected.clear()
        for var in self._select_vars.values():
            var.set(False)
        self._update_selection_buttons()
        self.status_var.set("Selection cleared.")

    def open_selected(self) -> None:
        tags = self._selected_tags()
        if not tags:
            return
        if len(tags) > 25:
            if not messagebox.askyesno(
                "Sparse Tag Browser",
                f"Open {len(tags)} tabs at once?\n\n"
                "Browsers may block or slow down with many tabs.",
            ):
                return
        self.open_tags(tags)

    def reset_walk(self) -> None:
        self._walk_index = 0
        self._update_walk_ui()
        self.status_var.set("Walk reset to top of list.")
        self._canvas.yview_moveto(0)

    def open_next_batch(self) -> None:
        visible = self._visible_tags()
        if not visible:
            return
        seen = self._seen_for()
        # Skip tags already opened earlier (manual click or prior walk).
        while self._walk_index < len(visible) and visible[self._walk_index].name in seen:
            self._walk_index += 1
        if self._walk_index >= len(visible):
            self.status_var.set("Walk finished — Reset walk or Load a new batch.")
            self._update_walk_ui()
            return
        ws = self.walk_size()
        chunk: list[SparseTag] = []
        i = self._walk_index
        while i < len(visible) and len(chunk) < ws:
            tag = visible[i]
            i += 1
            if tag.name in seen:
                continue
            chunk.append(tag)
        self._walk_index = i
        if not chunk:
            self.status_var.set("Walk finished — Reset walk or Load a new batch.")
            self._update_walk_ui()
            return
        self.open_tags(
            chunk, scroll_to=chunk[0].name, scroll_end=chunk[-1].name
        )
        self._update_walk_ui()

    def open_tags(
        self,
        tags: list[SparseTag],
        *,
        scroll_to: str | None = None,
        scroll_end: str | None = None,
    ) -> None:
        """Open each tag's posts URL; stagger to reduce popup-blocker / rate-limit issues."""
        if not tags:
            return
        # Rule34 rate-limits burst tab opens; Danbooru is fine at a shorter gap.
        source = tags[0].source
        gap_ms = 900 if source == "rule34" else 200
        opened_names = [t.name for t in tags]

        def _open_one(u: str, name: str) -> None:
            webbrowser.open(u)
            # Count as opened only when we actually fire the posts URL.
            mark_opened(self._seen, source, [name])

        for i, tag in enumerate(tags):
            self.after(
                i * gap_ms,
                lambda u=tag.posts_url, n=tag.name: _open_one(u, n),
            )
        delay = max(1, len(tags)) * gap_ms + 50
        self.after(
            delay,
            lambda n=len(tags), s=scroll_to, e=scroll_end, names=opened_names: self._mark_opened_inplace(
                names, n, s, e
            ),
        )
        gap_note = f" (~{gap_ms}ms apart)" if source == "rule34" and len(tags) > 1 else ""
        self.status_var.set(f"Opening {len(tags)} {source} tag(s){gap_note}…")

    def _scroll_batch_into_view(
        self, first_name: str, last_name: str | None = None
    ) -> None:
        """Scroll so the opened batch is pinned near the top of the viewport."""
        first = self._row_by_name.get(first_name)
        if first is None:
            return
        self._rows.update_idletasks()
        self._canvas.update_idletasks()
        total = max(1, int(self._rows.winfo_height()))
        view = max(1, int(self._canvas.winfo_height()))
        y0 = int(first.winfo_y())
        # Pin the first opened tag near the top so the rest of the batch reads downward.
        # Use total height (not total-view) — yview_moveto is fraction of full content.
        top = max(0, min(y0, max(0, total - view)))
        self._canvas.yview_moveto(top / total)

    def _mark_opened_inplace(
        self,
        names: list[str],
        n: int,
        scroll_to: str | None,
        scroll_end: str | None = None,
    ) -> None:
        for name in names:
            lbl = self._name_lbls.get(name)
            if lbl is not None:
                lbl.configure(text=f"{name}  ✓")
        self._update_status_line()
        self._update_walk_ui()
        if scroll_to:
            self._scroll_batch_into_view(scroll_to, scroll_end)
        self.status_var.set(f"Opened {n} tag(s).")

    def open_tag_posts(self, tag: SparseTag) -> None:
        self.open_tags([tag], scroll_to=tag.name, scroll_end=tag.name)

    def _toggle_fav(self, tag: SparseTag) -> None:
        now_on = toggle_favourite(self._favs, tag)
        btn = self._fav_btns.get(tag.name)
        if btn is not None:
            btn.configure(text="★" if now_on else "☆")
        self._update_status_line()
        if self._fav_window and self._fav_window.winfo_exists():
            self._fav_window.on_fav_changed(tag, now_on)
        verb = "Favourited" if now_on else "Removed"
        self.status_var.set(f"{verb}: {tag.name}")

    def open_favourites(self) -> None:
        if self._fav_window and self._fav_window.winfo_exists():
            self._fav_window.lift()
            self._fav_window.focus_force()
            return
        self._fav_window = FavouritesWindow(self)

    def check_updates(self, *, silent: bool = False) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        threading.Thread(
            target=self._check_updates_thread, args=(silent,), daemon=True
        ).start()

    def _check_updates_thread(self, silent: bool) -> None:
        from sparse_tags.updater import check_for_update, load_update_config

        try:
            info = check_for_update(load_update_config())
        except Exception as exc:
            self._update_busy = False
            if not silent:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Sparse Tag Browser", f"Update check failed:\n{exc}"
                    ),
                )
            return
        if info is None:
            self._update_busy = False
            if not silent:
                self.after(
                    0,
                    lambda: (
                        self.status_var.set(f"Up to date (v{__version__})"),
                        messagebox.showinfo(
                            "Sparse Tag Browser",
                            f"You're on the latest version (v{__version__}).",
                        ),
                    ),
                )
            return

        def _ask() -> None:
            ok = messagebox.askyesno(
                "Sparse Tag Browser",
                f"Version {info.version} is available (you have {__version__}).\n\n"
                "Download and install now?\n\n"
                "The app will close. After that, start Sparse Tag Browser.exe yourself "
                "(the install folder will open).",
            )
            if not ok:
                self._update_busy = False
                return
            self.status_var.set(f"Downloading v{info.version}…")
            threading.Thread(
                target=self._download_update_thread, args=(info,), daemon=True
            ).start()

        self.after(0, _ask)

    def _download_update_thread(self, info: Any) -> None:
        from sparse_tags.updater import load_update_config, run_update

        try:
            run_update(load_update_config(), info)
        except Exception as exc:
            self._update_busy = False
            self.after(
                0,
                lambda: (
                    self.status_var.set(f"Update failed: {exc}"),
                    messagebox.showerror("Sparse Tag Browser", f"Update failed:\n{exc}"),
                ),
            )
            return
        if getattr(sys, "frozen", False):

            def _done() -> None:
                self.status_var.set(f"Installed v{info.version} — start again.")
                messagebox.showinfo(
                    "Sparse Tag Browser",
                    f"Version {info.version} is ready.\n\n"
                    "This window will close. Then double-click Sparse Tag Browser.exe "
                    "in the folder that opens (or use your usual shortcut).",
                )
                self.after(400, self.destroy)

            self.after(0, _done)
        else:
            self._update_busy = False
            self.after(
                0,
                lambda: (
                    self.status_var.set(
                        f"Dev mode: update downloaded (v{info.version}); not applied."
                    ),
                    messagebox.showinfo(
                        "Sparse Tag Browser",
                        f"Dev mode: downloaded v{info.version} beside the project "
                        "(frozen exe would swap itself).",
                    ),
                ),
            )

    def shuffle_list(self) -> None:
        random.shuffle(self._tags)
        self._walk_index = 0
        self._refresh_list()

    def start_load(self) -> None:
        self._selected.clear()
        self._walk_index = 0
        if self._worker and self._worker.is_alive():
            return
        source = self._current_source()
        if not has_auth_for(source):
            if source == "rule34":
                messagebox.showwarning(
                    "Sparse Tag Browser",
                    "Rule34 API keys not found.\n\n"
                    "Open Conjure Finder → Settings… (same folder), "
                    "save API key + user id into conjure_finder.env, then try again.",
                )
            else:
                messagebox.showwarning(
                    "Sparse Tag Browser",
                    "Danbooru API keys not found.\n\n"
                    "Open Conjure Finder → Settings… (same folder), "
                    "save username + API key into conjure_finder.env, then try again.",
                )
            return
        try:
            min_c = int(self.min_var.get())
            max_c = int(self.max_var.get())
            batch = int(self.batch_var.get())
        except (tk.TclError, TypeError, ValueError):
            messagebox.showerror("Sparse Tag Browser", "Invalid number in pool filter.")
            return
        if min_c < 1 or max_c < min_c:
            messagebox.showerror(
                "Sparse Tag Browser", "Need 1 ≤ min posts ≤ max posts."
            )
            return

        self._persist_prefs()
        self._cancel.clear()
        self.load_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.status_var.set(f"Loading {source}…")

        req = FetchRequest(
            source=source,
            min_count=min_c,
            max_count=max_c,
            batch_size=batch,
            exclude_cosplay=bool(self.no_cosplay_var.get()),
            exclude_deprecated=bool(self.no_deprecated_var.get()),
        )

        def work() -> None:
            err: str | None = None
            tags: list[SparseTag] = []
            try:
                tags = fetch_sparse_tags_sync(
                    req,
                    progress=lambda msg: self.after(0, lambda m=msg: self.status_var.set(m)),
                    cancel_check=self._cancel.is_set,
                )
            except Exception as e:
                err = str(e)
            self.after(0, lambda: self._on_load_done(tags, err))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def cancel_load(self) -> None:
        self._cancel.set()
        self.status_var.set("Cancelling…")

    def _on_load_done(self, tags: list[SparseTag], err: str | None) -> None:
        self.load_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        if err:
            self.status_var.set(f"Error: {err}")
            messagebox.showerror("Sparse Tag Browser", err)
            return
        if self._cancel.is_set() and not tags:
            self.status_var.set("Cancelled.")
            return
        self._tags = [t for t in tags if t.name not in self._seen_for(t.source)]
        skipped = len(tags) - len(self._tags)
        self._walk_index = 0
        self._refresh_list()
        if not self._tags:
            if tags and skipped:
                self.status_var.set(
                    f"All {len(tags)} fetched tag(s) were already opened in the browser. "
                    "Try Clear opened history, or a wider post-count range."
                )
            else:
                self.status_var.set(
                    "No tags found for that post-count range. Try a wider max."
                )
        elif skipped:
            self.status_var.set(
                f"Loaded {len(self._tags)} tag(s) "
                f"({skipped} previously opened in browser, skipped)."
            )


class FavouritesWindow(tk.Toplevel):
    """Separate favourites browser with a tab per booru + short notes."""

    def __init__(self, app: SparseTagBrowser) -> None:
        super().__init__(app)
        self.app = app
        self.title("Favourites")
        self.minsize(480, 360)
        try:
            self.geometry(str(app._prefs.get("fav_geometry") or "560x520"))
        except tk.TclError:
            self.geometry("560x520")

        self._selected: set[str] = set()
        self._select_vars: dict[str, tk.BooleanVar] = {}
        self._fav_btns: dict[str, ttk.Button] = {}
        self._note_lbls: dict[str, tk.Label] = {}
        self._row_by_name: dict[str, tk.Frame] = {}
        self._empty_lbls: dict[Source, tk.Label | None] = {
            "danbooru": None,
            "rule34": None,
        }
        self._walk_index: dict[Source, int] = {"danbooru": 0, "rule34": 0}

        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(bar, text="Open next").pack(side=tk.LEFT)
        self.walk_size_var = tk.IntVar(value=app.walk_size())
        themed_spinbox(
            bar, from_=1, to=50, width=4, textvariable=self.walk_size_var
        ).pack(side=tk.LEFT, padx=(6, 4))
        self.open_next_btn = ttk.Button(
            bar, text="Open next batch", command=self.open_next_batch
        )
        self.open_next_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.reset_walk_btn = ttk.Button(bar, text="Reset walk", command=self.reset_walk)
        self.reset_walk_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.walk_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.walk_var).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(bar, text="Sort").pack(side=tk.LEFT, padx=(16, 4))
        initial_sort = str(app._prefs.get("fav_sort") or "favourited")
        if initial_sort not in ("alpha", "favourited"):
            initial_sort = "favourited"
        self._sort_labels = {
            "favourited": "Favourited order",
            "alpha": "A–Z",
        }
        self._sort_keys = {v: k for k, v in self._sort_labels.items()}
        self.sort_var = tk.StringVar(value=self._sort_labels[initial_sort])
        self.sort_box = ttk.Combobox(
            bar,
            textvariable=self.sort_var,
            values=tuple(self._sort_labels.values()),
            state="readonly",
            width=16,
        )
        self.sort_box.pack(side=tk.LEFT)
        self.sort_box.bind("<<ComboboxSelected>>", lambda _e: self._on_sort_change())

        self.open_sel_btn = ttk.Button(
            bar, text="Open selected", command=self.open_selected, state=tk.DISABLED
        )
        self.open_sel_btn.pack(side=tk.RIGHT)
        self.clear_sel_btn = ttk.Button(
            bar, text="Clear selection", command=self.clear_selection, state=tk.DISABLED
        )
        self.clear_sel_btn.pack(side=tk.RIGHT, padx=(0, 8))

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._notebook = nb
        self._canvases: dict[Source, tk.Canvas] = {}
        self._rows: dict[Source, tk.Frame] = {}

        for source, label in (("danbooru", "Danbooru"), ("rule34", "Rule34")):
            outer = ttk.Frame(nb)
            nb.add(outer, text=label)
            canvas = tk.Canvas(
                outer, highlightthickness=0, bg=surface_for(self)["canvas"]
            )
            rows = tk.Frame(canvas, bg=surface_for(self)["canvas"])
            rows.bind(
                "<Configure>",
                lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")),
            )
            win = canvas.create_window((0, 0), window=rows, anchor=tk.NW)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.bind(
                "<Configure>",
                lambda e, c=canvas, w=win: c.itemconfigure(w, width=e.width),
            )
            RegionMousewheel.register(self, canvas, outer)
            self._canvases[source] = canvas  # type: ignore[index]
            self._rows[source] = rows  # type: ignore[index]

        hint = ttk.Label(
            self,
            text="Note… adds a short label · ★ removes · zebra rows for clarity",
        )
        hint.pack(fill=tk.X, padx=10, pady=(0, 8))

        idx = 1 if app._current_source() == "rule34" else 0
        nb.select(idx)
        nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_changed())
        self.refresh()
        apply_app_theme(self)
        schedule_theme_refresh(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def walk_size(self) -> int:
        try:
            return max(1, min(50, int(self.walk_size_var.get())))
        except (tk.TclError, TypeError, ValueError):
            return self.app.walk_size()

    def fav_sort(self) -> str:
        return self._sort_keys.get(self.sort_var.get(), "favourited")

    def _on_sort_change(self) -> None:
        self.app._prefs["fav_sort"] = self.fav_sort()
        self.app._schedule_save_prefs()
        for source in ("danbooru", "rule34"):
            self._walk_index[source] = 0  # type: ignore[index]
        self.refresh()
        source = self._current_source()
        self._canvases[source].yview_moveto(0)

    def _entries(self, source: Source) -> list[FavEntry]:
        return sorted_fav_entries(
            self.app._favs.get(source, []), sort=self.fav_sort()
        )

    def _on_tab_changed(self) -> None:
        self._update_selection_buttons()
        self._update_walk_ui()

    def _current_source(self) -> Source:
        try:
            tab = self._notebook.index(self._notebook.select())
        except tk.TclError:
            return "danbooru"
        return "rule34" if tab == 1 else "danbooru"

    def _update_selection_buttons(self) -> None:
        source = self._current_source()
        names = {e.tag.name for e in self._entries(source)}
        active = bool(self._selected & names)
        state = tk.NORMAL if active else tk.DISABLED
        self.open_sel_btn.configure(state=state)
        self.clear_sel_btn.configure(state=state)

    def _update_walk_ui(self) -> None:
        source = self._current_source()
        tags = fav_tags(self.app._favs, source, sort=self.fav_sort())
        total = len(tags)
        at = min(self._walk_index.get(source, 0), total)
        remaining = max(0, total - at)
        ws = self.walk_size()
        if total == 0:
            self.walk_var.set("Walk: —")
            self.open_next_btn.configure(state=tk.DISABLED)
            self.reset_walk_btn.configure(state=tk.DISABLED)
            return
        self.reset_walk_btn.configure(state=tk.NORMAL)
        if remaining == 0:
            self.walk_var.set(f"Walk: done ({total}/{total})")
            self.open_next_btn.configure(state=tk.DISABLED)
        else:
            nxt = min(ws, remaining)
            self.walk_var.set(f"Walk: next {nxt} · at {at}/{total}")
            self.open_next_btn.configure(state=tk.NORMAL)

    def clear_selection(self) -> None:
        source = self._current_source()
        names = {e.tag.name for e in self._entries(source)}
        self._selected -= names
        for name, var in self._select_vars.items():
            if name in names:
                var.set(False)
        self._update_selection_buttons()

    def open_selected(self) -> None:
        source = self._current_source()
        by_name = {e.tag.name: e.tag for e in self._entries(source)}
        tags = [by_name[n] for n in by_name if n in self._selected]
        if not tags:
            return
        if len(tags) > 25:
            if not messagebox.askyesno(
                "Favourites",
                f"Open {len(tags)} tabs at once?",
            ):
                return
        self.app.open_tags(tags)

    def reset_walk(self) -> None:
        source = self._current_source()
        self._walk_index[source] = 0
        self._update_walk_ui()
        self._canvases[source].yview_moveto(0)

    def open_next_batch(self) -> None:
        source = self._current_source()
        tags = fav_tags(self.app._favs, source, sort=self.fav_sort())
        if not tags:
            return
        idx = self._walk_index.get(source, 0)
        if idx >= len(tags):
            self._update_walk_ui()
            return
        ws = self.walk_size()
        chunk = tags[idx : idx + ws]
        self._walk_index[source] = idx + len(chunk)
        scroll_first = chunk[0].name if chunk else None
        scroll_last = chunk[-1].name if chunk else None
        self.app.open_tags(chunk, scroll_to=None)
        if scroll_first:
            self.after(
                50,
                lambda f=scroll_first, l=scroll_last, s=source: self._scroll_batch_into_view(
                    s, f, l
                ),
            )
        self._update_walk_ui()

    def _scroll_batch_into_view(
        self, source: Source, first_name: str, last_name: str | None = None
    ) -> None:
        first = self._row_by_name.get(first_name)
        canvas = self._canvases[source]
        rows = self._rows[source]
        if first is None:
            return
        rows.update_idletasks()
        canvas.update_idletasks()
        total = max(1, int(rows.winfo_height()))
        view = max(1, int(canvas.winfo_height()))
        y0 = int(first.winfo_y())
        top = max(0, min(y0, max(0, total - view)))
        canvas.yview_moveto(top / total)

    def refresh(self) -> None:
        all_names = {
            e.tag.name
            for src in ("danbooru", "rule34")
            for e in self.app._favs.get(src, [])  # type: ignore[arg-type]
        }
        self._selected &= all_names
        self._select_vars.clear()
        self._fav_btns.clear()
        self._note_lbls.clear()
        self._row_by_name.clear()
        for source in ("danbooru", "rule34"):
            rows = self._rows[source]  # type: ignore[index]
            canvas = self._canvases[source]  # type: ignore[index]
            c = surface_for(self)
            try:
                rows.configure(bg=c["canvas"])
                canvas.configure(bg=c["canvas"])
            except tk.TclError:
                pass
            for child in list(rows.winfo_children()):
                child.destroy()
            self._empty_lbls[source] = None  # type: ignore[index]
            entries = self._entries(source)  # type: ignore[arg-type]
            if not entries:
                c = surface_for(self)
                lbl = tk.Label(
                    rows,
                    text="(none yet)",
                    bg=c["canvas"],
                    fg=c["muted"],
                    anchor=tk.W,
                )
                lbl._sparse_row_tint = True  # type: ignore[attr-defined]
                lbl.pack(anchor=tk.W, padx=6, pady=8)
                self._empty_lbls[source] = lbl  # type: ignore[index]
            else:
                for i, entry in enumerate(entries):
                    self._add_row(rows, entry, index=i)
            label = "Danbooru" if source == "danbooru" else "Rule34"
            self._notebook.tab(
                0 if source == "danbooru" else 1,
                text=f"{label} ({len(entries)})",
            )
            wi = self._walk_index.get(source, 0)  # type: ignore[arg-type]
            if wi > len(entries):
                self._walk_index[source] = 0  # type: ignore[index]
        self._update_selection_buttons()
        self._update_walk_ui()

    def on_fav_changed(self, tag: SparseTag, now_on: bool) -> None:
        # Rebuild so alphabetical / favourited order stays correct.
        self.refresh()
        if not now_on:
            self._selected.discard(tag.name)
    def _add_row(self, parent: tk.Frame, entry: FavEntry, *, index: int) -> None:
        tag = entry.tag
        c = surface_for(self)
        bg = zebra(index, self)
        row = tk.Frame(parent, bg=bg, highlightthickness=0)
        row.pack(fill=tk.X, pady=0, padx=0, ipady=2)
        self._row_by_name[tag.name] = row
        var = tk.BooleanVar(value=tag.name in self._selected)
        self._select_vars[tag.name] = var
        cb = tk.Checkbutton(
            row,
            variable=var,
            command=lambda t=tag, v=var: self._on_select_toggle(t, v),
            bg=bg,
            fg=c["fg"],
            activebackground=bg,
            activeforeground=c["fg"],
            selectcolor=c["entry"],
            highlightthickness=0,
            bd=0,
        )
        cb._sparse_row_tint = True  # type: ignore[attr-defined]
        cb.pack(side=tk.LEFT, padx=(4, 0))
        count_btn = tk.Button(
            row,
            text=str(tag.post_count),
            width=5,
            command=lambda t=tag: self.app.open_tag_posts(t),
            relief=tk.FLAT,
            bg=c["button"],
            fg=c["fg"],
            activebackground=c["button_active"],
            activeforeground=c["fg"],
            bd=0,
            highlightthickness=0,
        )
        count_btn._sparse_custom_btn = True  # type: ignore[attr-defined]
        count_btn.pack(side=tk.LEFT, padx=(2, 0))
        name_lbl = tk.Label(
            row,
            text=tag.name,
            font=("Consolas", 11),
            bg=bg,
            fg=c["fg"],
            anchor=tk.W,
        )
        name_lbl._sparse_row_tint = True  # type: ignore[attr-defined]
        name_lbl.pack(side=tk.LEFT, padx=(8, 4))
        name_lbl.bind("<Button-1>", lambda _e, t=tag, v=var: self._toggle_row_select(t, v))

        note_text = entry.note if entry.note else ""
        note_lbl = tk.Label(
            row,
            text=f"— {note_text}" if note_text else "",
            font=("Segoe UI", 9),
            fg=c["muted"],
            bg=bg,
            anchor=tk.W,
        )
        note_lbl._sparse_row_tint = True  # type: ignore[attr-defined]
        note_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._note_lbls[tag.name] = note_lbl

        ttk.Button(
            row,
            text="Note…",
            width=6,
            command=lambda t=tag: self._edit_note(t),
        ).pack(side=tk.RIGHT, padx=(0, 2))
        fav_btn = ttk.Button(
            row,
            text="★",
            width=3,
            command=lambda t=tag: self.app._toggle_fav(t),
        )
        fav_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self._fav_btns[tag.name] = fav_btn

    def _edit_note(self, tag: SparseTag) -> None:
        current = get_note(self.app._favs, tag.source, tag.name)
        result = simpledialog.askstring(
            "Favourite note",
            f"Short note for {tag.name}:",
            initialvalue=current,
            parent=self,
        )
        if result is None:
            return
        set_note(self.app._favs, tag.source, tag.name, result)
        lbl = self._note_lbls.get(tag.name)
        note = get_note(self.app._favs, tag.source, tag.name)
        if lbl is not None:
            lbl.configure(text=f"— {note}" if note else "")

    def _on_select_toggle(self, tag: SparseTag, var: tk.BooleanVar) -> None:
        if var.get():
            self._selected.add(tag.name)
        else:
            self._selected.discard(tag.name)
        self._update_selection_buttons()

    def _toggle_row_select(self, tag: SparseTag, var: tk.BooleanVar) -> None:
        var.set(not var.get())
        self._on_select_toggle(tag, var)

    def _on_close(self) -> None:
        try:
            self.app._prefs["fav_geometry"] = self.geometry()
            self.app._persist_prefs()
        except Exception:
            pass
        self.app._fav_window = None
        self.destroy()
