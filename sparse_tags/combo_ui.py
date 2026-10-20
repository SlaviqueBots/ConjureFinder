"""Combo-search tab: pair a prompt tag with permanently recorded partners."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from sparse_tags.combo import (
    ComboState,
    DEFAULT_R34_NEGATIVES,
    add_r34_negative,
    add_recorded,
    build_combo_queries,
    is_recorded_enabled,
    load_combo,
    normalize_tag,
    recorded_tags_text,
    remove_r34_negative,
    remove_recorded,
    save_combo,
    set_mode,
    set_many_recorded_enabled,
    set_r34_negatives,
    set_rating,
    set_recorded_enabled,
)
from sparse_tags.theme import (
    RegionMousewheel,
    bind_entry_clipboard,
    bind_text_clipboard,
    schedule_theme_refresh,
    style_on_off_button,
    surface_for,
    zebra,
)


class ComboSearchPanel(ttk.Frame):
    """Danbooru / Rule34 pair-open UI living inside a notebook tab."""

    def __init__(self, master: tk.Misc, *, host: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self._host = host
        self._state: ComboState = load_combo()
        self._row_by_name: dict[str, tk.Frame] = {}
        self._neg_row_by_name: dict[str, tk.Frame] = {}
        self._on_btns: dict[str, tk.Button] = {}
        self._name_lbls: dict[str, tk.Label] = {}
        self._tags_window: tk.Toplevel | None = None
        self._ordered: list[str] = []
        self._selected: set[str] = set()
        self._anchor_index: int = 0
        self._focus_index: int = 0

        self._build()
        self._apply_mode_visibility()
        self._refresh_recorded()
        self._refresh_negatives()
        self._bind_list_keys()

    def _colors(self) -> dict[str, str]:
        return surface_for(self._host)

    def _build(self) -> None:
        pad = {"padx": 4, "pady": 4}
        c = self._colors()

        mode_box = ttk.LabelFrame(self, text="Site", padding=8)
        mode_box.pack(fill=tk.X, **pad)
        self.mode_var = tk.StringVar(value=self._state.mode)
        ttk.Radiobutton(
            mode_box,
            text="Danbooru",
            value="danbooru",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_box,
            text="Rule34",
            value="rule34",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(
            mode_box,
            text="Each site keeps its own partner pool. Opens one tab per On partner.",
        ).pack(side=tk.LEFT, padx=(16, 0))

        prompt = ttk.LabelFrame(self, text="Prompt tag", padding=8)
        prompt.pack(fill=tk.X, **pad)
        ttk.Label(prompt, text="New tag").pack(side=tk.LEFT)
        self.input_var = tk.StringVar()
        entry = ttk.Entry(prompt, textvariable=self.input_var, width=36)
        entry.pack(side=tk.LEFT, padx=(8, 8), fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self.open_combos())
        bind_entry_clipboard(entry)
        self.open_btn = ttk.Button(
            prompt, text="Open all combos", command=self.open_combos
        )
        self.open_btn.pack(side=tk.RIGHT)

        self._rating_box = ttk.LabelFrame(
            self, text="Danbooru rating (optional 3rd tag)", padding=8
        )
        self._rating_box.pack(fill=tk.X, **pad)
        self.rating_var = tk.StringVar(value=self._state.rating or "off")
        for label, value in (
            ("Off", "off"),
            ("G", "g"),
            ("S", "s"),
            ("Q", "q"),
            ("E", "e"),
        ):
            ttk.Radiobutton(
                self._rating_box,
                text=label,
                value=value,
                variable=self.rating_var,
                command=self._on_rating_change,
            ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(
            self._rating_box,
            text="e.g. input partner rating:g",
        ).pack(side=tk.LEFT, padx=(8, 0))

        self._neg_box = ttk.LabelFrame(
            self, text="Rule34 negatives (appended to every search)", padding=8
        )
        neg_bar = ttk.Frame(self._neg_box)
        neg_bar.pack(fill=tk.X, pady=(0, 4))
        self.neg_input_var = tk.StringVar()
        neg_entry = ttk.Entry(neg_bar, textvariable=self.neg_input_var, width=24)
        neg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        neg_entry.bind("<Return>", lambda _e: self._add_negative())
        bind_entry_clipboard(neg_entry)
        ttk.Button(neg_bar, text="Add −tag", command=self._add_negative).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(
            neg_bar, text="Reset defaults", command=self._reset_negatives
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._neg_rows = tk.Frame(self._neg_box, bg=c["canvas"])
        self._neg_rows.pack(fill=tk.X)

        self._rec_box = ttk.LabelFrame(
            self, text="Recorded partners (kept forever · per site)", padding=8
        )
        self._rec_box.pack(fill=tk.BOTH, expand=True, **pad)
        add_bar = ttk.Frame(self._rec_box)
        add_bar.pack(fill=tk.X, pady=(0, 4))
        self.record_input_var = tk.StringVar()
        rec_entry = ttk.Entry(add_bar, textvariable=self.record_input_var, width=28)
        rec_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        rec_entry.bind("<Return>", lambda _e: self._add_recorded())
        bind_entry_clipboard(rec_entry)
        ttk.Button(add_bar, text="Record tag", command=self._add_recorded).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(
            add_bar, text="Show all tags…", command=self.show_all_tags
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            add_bar, text="Toggle On/Off", command=self._toggle_selected_enabled
        ).pack(side=tk.RIGHT)

        list_frame = ttk.Frame(self._rec_box)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self._list_frame = list_frame
        self._canvas = tk.Canvas(
            list_frame, highlightthickness=0, bg=c["canvas"], height=180
        )
        self._rows = tk.Frame(self._canvas, bg=c["canvas"])
        self._rows.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._rows, anchor=tk.NW
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        RegionMousewheel.register(self._host, self._canvas, list_frame)
        # Click empty list area to focus keyboard nav.
        self._canvas.bind("<Button-1>", lambda _e: self._focus_list())
        self._rows.bind("<Button-1>", lambda _e: self._focus_list())

        self.status_var = tk.StringVar(
            value=(
                "Record partners (new tags start On). "
                "↑↓ move · Shift+↑↓/click range · Space/Enter toggle On/Off · "
                "separate pools per site."
            )
        )
        ttk.Label(self, textvariable=self.status_var, wraplength=680).pack(
            fill=tk.X, anchor=tk.W, pady=(6, 0)
        )

    def _bind_list_keys(self) -> None:
        for seq, handler in (
            ("<Up>", lambda e: self._move_focus(-1, e)),
            ("<Down>", lambda e: self._move_focus(1, e)),
            ("<Shift-Up>", lambda e: self._move_focus(-1, e)),
            ("<Shift-Down>", lambda e: self._move_focus(1, e)),
            ("<space>", lambda _e: self._toggle_selected_enabled() or "break"),
            ("<Return>", lambda _e: self._toggle_selected_enabled() or "break"),
            ("<Control-a>", lambda _e: self._select_all() or "break"),
            ("<Control-A>", lambda _e: self._select_all() or "break"),
            ("<Escape>", lambda _e: self._clear_selection() or "break"),
        ):
            self._canvas.bind(seq, handler)
            self._rows.bind(seq, handler)

    def _focus_list(self) -> None:
        try:
            self._canvas.focus_set()
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _current_mode(self) -> str:
        raw = (self.mode_var.get() or "danbooru").strip().lower()
        return "rule34" if raw == "rule34" else "danbooru"

    def _on_mode_change(self) -> None:
        mode = self._current_mode()
        set_mode(self._state, "rule34" if mode == "rule34" else "danbooru")
        self._apply_mode_visibility()
        self._selected.clear()
        self._focus_index = 0
        self._anchor_index = 0
        self._refresh_recorded()
        label = "Rule34" if mode == "rule34" else "Danbooru"
        n = len(self._state.recorded)
        self.status_var.set(
            f"{label} pool — {n} recorded partner(s). "
            + (
                "Negatives appended to every search."
                if mode == "rule34"
                else "Optional rating metatag."
            )
        )

    def _apply_mode_visibility(self) -> None:
        mode = self._current_mode()
        self._rating_box.pack_forget()
        self._neg_box.pack_forget()
        if mode == "rule34":
            self._neg_box.pack(
                fill=tk.BOTH, padx=4, pady=4, before=self._rec_box
            )
        else:
            self._rating_box.pack(
                fill=tk.X, padx=4, pady=4, before=self._rec_box
            )

    def _on_rating_change(self) -> None:
        raw = (self.rating_var.get() or "off").strip().lower()
        rating = "" if raw in ("", "off") else raw
        if rating not in ("", "g", "s", "q", "e"):
            rating = ""
        set_rating(self._state, rating)  # type: ignore[arg-type]
        if rating:
            self.status_var.set(f"Rating filter on: rating:{rating}")
        else:
            self.status_var.set("Rating filter off.")

    def _add_recorded(self) -> None:
        raw = self.record_input_var.get()
        name = add_recorded(self._state, raw)
        if name is None:
            cleaned = normalize_tag(raw)
            if not cleaned:
                messagebox.showinfo(
                    "Combo search", "Enter a tag to record.", parent=self._host
                )
            else:
                messagebox.showinfo(
                    "Combo search",
                    f"Already recorded: {cleaned}",
                    parent=self._host,
                )
            return
        self.record_input_var.set("")
        self._refresh_recorded()
        self._refresh_tags_window()
        on_n = len(self._state.enabled)
        self.status_var.set(
            f"Recorded On: {name}  ({on_n}/{len(self._state.recorded)} On)"
        )

    def _remove_one(self, name: str) -> None:
        if not messagebox.askyesno(
            "Combo search",
            f"Remove recorded tag “{name}”?",
            parent=self._host,
        ):
            return
        remove_recorded(self._state, name)
        self._selected.discard(name)
        self._refresh_recorded()
        self._refresh_tags_window()
        self.status_var.set(f"Removed: {name}")

    def _set_one_enabled(self, name: str, on: bool) -> None:
        set_recorded_enabled(self._state, name, on)
        btn = self._on_btns.get(name)
        if btn is not None:
            style_on_off_button(btn, on=on, colors=self._colors())
        on_n = len(self._state.enabled)
        state = "On" if on else "Off"
        self.status_var.set(
            f"{name}: {state}  ({on_n}/{len(self._state.recorded)} On)"
        )

    def _toggle_one_enabled(self, name: str) -> None:
        self._set_one_enabled(name, not is_recorded_enabled(self._state, name))

    def _toggle_selected_enabled(self) -> None:
        names = [n for n in self._ordered if n in self._selected]
        if not names:
            if 0 <= self._focus_index < len(self._ordered):
                names = [self._ordered[self._focus_index]]
                self._selected = {names[0]}
                self._paint_selection()
            else:
                return
        # Bulk: if any Off → turn all On; else turn all Off.
        any_off = any(not is_recorded_enabled(self._state, n) for n in names)
        target = any_off
        set_many_recorded_enabled(self._state, names, target)
        for n in names:
            btn = self._on_btns.get(n)
            if btn is not None:
                style_on_off_button(
                    btn, on=is_recorded_enabled(self._state, n), colors=self._colors()
                )
        on_n = len(self._state.enabled)
        verb = "On" if target else "Off"
        self.status_var.set(
            f"{len(names)} tag(s) → {verb}  ({on_n}/{len(self._state.recorded)} On)"
        )

    def _select_all(self) -> None:
        self._selected = set(self._ordered)
        if self._ordered:
            self._focus_index = 0
            self._anchor_index = 0
        self._paint_selection()

    def _clear_selection(self) -> None:
        self._selected.clear()
        self._paint_selection()

    def _move_focus(self, delta: int, event: tk.Event | None = None) -> str:
        if not self._ordered:
            return "break"
        self._focus_list()
        nxt = max(0, min(len(self._ordered) - 1, self._focus_index + delta))
        shift = False
        if event is not None:
            try:
                shift = bool(event.state & 0x0001)
            except Exception:
                shift = False
        self._focus_index = nxt
        if shift:
            lo = min(self._anchor_index, nxt)
            hi = max(self._anchor_index, nxt)
            self._selected = set(self._ordered[lo : hi + 1])
        else:
            self._anchor_index = nxt
            self._selected = {self._ordered[nxt]}
        self._paint_selection()
        self._scroll_focus_into_view()
        return "break"

    def _scroll_focus_into_view(self) -> None:
        if not (0 <= self._focus_index < len(self._ordered)):
            return
        name = self._ordered[self._focus_index]
        row = self._row_by_name.get(name)
        if row is None:
            return
        self._rows.update_idletasks()
        self._canvas.update_idletasks()
        total = max(1, int(self._rows.winfo_height()))
        view = max(1, int(self._canvas.winfo_height()))
        y0 = int(row.winfo_y())
        y1 = y0 + int(row.winfo_height())
        top = self._canvas.canvasy(0)
        bottom = top + view
        if y0 < top:
            self._canvas.yview_moveto(max(0, y0) / total)
        elif y1 > bottom:
            self._canvas.yview_moveto(max(0, y1 - view) / total)

    def _row_click(self, name: str, event: tk.Event) -> None:
        if name not in self._ordered:
            return
        idx = self._ordered.index(name)
        self._focus_list()
        shift = bool(getattr(event, "state", 0) & 0x0001)
        ctrl = bool(getattr(event, "state", 0) & 0x0004)
        self._focus_index = idx
        if shift:
            lo = min(self._anchor_index, idx)
            hi = max(self._anchor_index, idx)
            self._selected = set(self._ordered[lo : hi + 1])
        elif ctrl:
            if name in self._selected:
                self._selected.discard(name)
            else:
                self._selected.add(name)
            self._anchor_index = idx
        else:
            self._anchor_index = idx
            self._selected = {name}
        self._paint_selection()

    def _row_bg(self, name: str, index: int) -> str:
        c = self._colors()
        if name in self._selected:
            return c["select"]
        return zebra(index, self._host)

    def _paint_selection(self) -> None:
        for i, name in enumerate(self._ordered):
            row = self._row_by_name.get(name)
            if row is None:
                continue
            bg = self._row_bg(name, i)
            try:
                row.configure(bg=bg)
            except tk.TclError:
                continue
            for child in row.winfo_children():
                cls = child.winfo_class()
                if cls in ("Label", "Frame"):
                    try:
                        child.configure(bg=bg)  # type: ignore[call-arg]
                    except tk.TclError:
                        pass
                if cls == "Button" and child is self._on_btns.get(name):
                    # Keep On/Off colors; only leave custom flag.
                    continue

    def _refresh_recorded(self) -> None:
        self._on_btns.clear()
        self._name_lbls.clear()
        self._row_by_name.clear()
        for child in list(self._rows.winfo_children()):
            child.destroy()
        c = self._colors()
        self._rows.configure(bg=c["canvas"])
        self._ordered = list(self._state.recorded)
        self._selected &= set(self._ordered)
        if self._focus_index >= len(self._ordered):
            self._focus_index = max(0, len(self._ordered) - 1)
        if self._anchor_index >= len(self._ordered):
            self._anchor_index = self._focus_index
        if not self._ordered:
            empty = tk.Label(
                self._rows,
                text=(
                    "(none yet — record partners for this site; new ones start On)"
                ),
                bg=c["canvas"],
                fg=c["muted"],
                anchor=tk.W,
            )
            empty._sparse_row_tint = True  # type: ignore[attr-defined]
            empty.pack(anchor=tk.W, padx=6, pady=8)
            return
        for i, name in enumerate(self._ordered):
            self._add_recorded_row(name, index=i)
        self._paint_selection()

    def _add_recorded_row(self, name: str, *, index: int) -> None:
        bg = self._row_bg(name, index)
        row = tk.Frame(self._rows, bg=bg)
        row.pack(fill=tk.X, ipady=2)
        self._row_by_name[name] = row

        on = is_recorded_enabled(self._state, name)
        btn = tk.Button(
            row,
            width=4,
            command=lambda n=name: self._toggle_one_enabled(n),
        )
        style_on_off_button(btn, on=on, colors=self._colors())
        btn.pack(side=tk.LEFT, padx=(6, 0), pady=1)
        self._on_btns[name] = btn

        lbl = tk.Label(
            row, text=name, font=("Consolas", 11), bg=bg, fg=self._colors()["fg"], anchor=tk.W
        )
        lbl._sparse_row_tint = True  # type: ignore[attr-defined]
        lbl.pack(side=tk.LEFT, padx=(8, 4), fill=tk.X, expand=True)
        self._name_lbls[name] = lbl

        rm = ttk.Button(
            row, text="Remove", width=8, command=lambda n=name: self._remove_one(n)
        )
        rm.pack(side=tk.RIGHT, padx=(0, 4))

        for w in (row, lbl):
            w.bind("<Button-1>", lambda e, n=name: self._row_click(n, e))
            w.bind(
                "<Double-Button-1>",
                lambda _e, n=name: self._toggle_one_enabled(n),
            )

    def show_all_tags(self) -> None:
        """Window with one selectable/copyable line per recorded tag."""
        if self._tags_window is not None and self._tags_window.winfo_exists():
            self._refresh_tags_window()
            self._tags_window.lift()
            self._tags_window.focus_force()
            return

        win = tk.Toplevel(self._host)
        win.title("Recorded tags")
        win.minsize(320, 280)
        try:
            win.geometry("420x420")
        except tk.TclError:
            pass
        self._tags_window = win
        c = self._colors()
        try:
            win.configure(bg=c["bg"])
        except tk.TclError:
            pass

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="One tag per line — select and copy").pack(side=tk.LEFT)
        ttk.Button(bar, text="Copy all", command=self._copy_all_tags).pack(
            side=tk.RIGHT
        )

        text = tk.Text(
            win,
            wrap=tk.NONE,
            font=("Consolas", 11),
            undo=False,
            padx=8,
            pady=8,
            bg=c["log_bg"],
            fg=c["fg"],
            insertbackground=c["fg"],
            selectbackground=c["select"],
            selectforeground=c["fg"],
            relief=tk.FLAT,
            highlightthickness=0,
            bd=0,
        )
        yscroll = ttk.Scrollbar(win, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tags_text = text
        bind_text_clipboard(text)
        self._refresh_tags_window()
        win.protocol("WM_DELETE_WINDOW", self._close_tags_window)
        schedule_theme_refresh(win)

    def _close_tags_window(self) -> None:
        if self._tags_window is not None:
            try:
                self._tags_window.destroy()
            except tk.TclError:
                pass
        self._tags_window = None

    def _refresh_tags_window(self) -> None:
        if self._tags_window is None or not self._tags_window.winfo_exists():
            return
        text = getattr(self, "_tags_text", None)
        if text is None:
            return
        body = recorded_tags_text(self._state)
        text.configure(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        if body:
            text.insert("1.0", body)
        else:
            text.insert("1.0", "(no recorded tags yet)")

    def _copy_all_tags(self) -> None:
        body = recorded_tags_text(self._state)
        if not body:
            messagebox.showinfo(
                "Combo search", "No recorded tags to copy.", parent=self._host
            )
            return
        self._host.clipboard_clear()
        self._host.clipboard_append(body)
        self.status_var.set(f"Copied {len(self._state.recorded)} tag(s) to clipboard.")

    def _add_negative(self) -> None:
        raw = self.neg_input_var.get()
        name = add_r34_negative(self._state, raw)
        if name is None:
            cleaned = normalize_tag(raw)
            if not cleaned:
                messagebox.showinfo(
                    "Combo search", "Enter a negative tag.", parent=self._host
                )
            else:
                messagebox.showinfo(
                    "Combo search",
                    f"Already in list: -{cleaned}",
                    parent=self._host,
                )
            return
        self.neg_input_var.set("")
        self._refresh_negatives()
        self.status_var.set(f"Added negative: -{name}")

    def _remove_negative(self, name: str) -> None:
        remove_r34_negative(self._state, name)
        self._refresh_negatives()
        self.status_var.set(f"Removed negative: -{name}")

    def _reset_negatives(self) -> None:
        if not messagebox.askyesno(
            "Combo search",
            "Reset Rule34 negatives to -furry -anthro -guro?",
            parent=self._host,
        ):
            return
        set_r34_negatives(self._state, list(DEFAULT_R34_NEGATIVES))
        self._refresh_negatives()
        self.status_var.set("Negatives reset to defaults.")

    def _refresh_negatives(self) -> None:
        self._neg_row_by_name.clear()
        for child in list(self._neg_rows.winfo_children()):
            child.destroy()
        c = self._colors()
        self._neg_rows.configure(bg=c["canvas"])
        if not self._state.r34_negatives:
            lbl = tk.Label(
                self._neg_rows,
                text="(no negatives — every search is just input + partner)",
                bg=c["canvas"],
                fg=c["muted"],
                anchor=tk.W,
            )
            lbl._sparse_row_tint = True  # type: ignore[attr-defined]
            lbl.pack(anchor=tk.W, padx=2, pady=4)
            return
        for i, name in enumerate(self._state.r34_negatives):
            bg = zebra(i, self._host)
            row = tk.Frame(self._neg_rows, bg=bg)
            row.pack(fill=tk.X, ipady=1)
            self._neg_row_by_name[name] = row
            nl = tk.Label(
                row,
                text=f"-{name}",
                font=("Consolas", 10),
                bg=bg,
                fg=c["fg"],
                anchor=tk.W,
            )
            nl._sparse_row_tint = True  # type: ignore[attr-defined]
            nl.pack(side=tk.LEFT, padx=(4, 4), fill=tk.X, expand=True)
            ttk.Button(
                row,
                text="Remove",
                width=8,
                command=lambda n=name: self._remove_negative(n),
            ).pack(side=tk.RIGHT, padx=(0, 2))

    def open_combos(self) -> None:
        seed = normalize_tag(self.input_var.get())
        if not seed:
            messagebox.showinfo(
                "Combo search", "Enter a prompt tag first.", parent=self._host
            )
            return
        if not self._state.recorded:
            messagebox.showinfo(
                "Combo search",
                "Record at least one partner tag first.",
                parent=self._host,
            )
            return
        if not self._state.enabled:
            messagebox.showinfo(
                "Combo search",
                "Turn On at least one recorded partner.",
                parent=self._host,
            )
            return
        queries = build_combo_queries(seed, self._state)
        if not queries:
            messagebox.showinfo(
                "Combo search",
                "Nothing to open — the prompt matches every On partner.",
                parent=self._host,
            )
            return
        skipped = 1 if seed in self._state.enabled else 0
        n = len(queries)
        if n > 25:
            if not messagebox.askyesno(
                "Combo search",
                f"Open {n} browser tabs at once?",
                parent=self._host,
            ):
                return
        gap_ms = 900 if self._state.mode == "rule34" else 200

        def _open(url: str) -> None:
            webbrowser.open(url)

        for i, (_q, url) in enumerate(queries):
            self._host.after(i * gap_ms, lambda u=url: _open(u))
        note = " (skipped self-pair)" if skipped else ""
        sample = queries[0][0]
        self.status_var.set(
            f"Opening {n} {self._state.mode} search(es){note}…  e.g. {sample}"
        )

    def persist(self) -> None:
        save_combo(self._state)
