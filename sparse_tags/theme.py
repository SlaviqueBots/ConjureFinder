"""Bridge-matching dark chrome for Sparse Tag Browser (Discord/Cursor-ish)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Same palette as Harem Link Bridge dark mode.
DARK: dict[str, str] = {
    "mode": "dark",
    "bg": "#1e1f22",
    "bg2": "#2b2d31",
    "bg3": "#313338",
    "fg": "#f2f3f5",
    "muted": "#b5bac1",
    "border": "#1e1f22",
    "accent": "#5865f2",
    # Slightly inset from bg so Entry/Spinbox fields read as controls.
    "entry": "#131416",
    "select": "#404249",
    "trough": "#1e1f22",
    "tab": "#2b2d31",
    "tab_sel": "#313338",
    "button": "#2b2d31",
    "button_active": "#383a40",
    "log_bg": "#111214",
    "canvas": "#1e1f22",
    "hover": "#35373c",
    # Soft sage On toggle — low chroma, easy on dark UI.
    "on": "#3a4740",
    "on_active": "#46554c",
    "on_fg": "#c8d4cc",
    "off": "#3a3c41",
    "off_active": "#484a51",
    "zebra0": "#1e1f22",
    "zebra1": "#25262b",
    "input_border": "#3f4147",
}


def palette() -> dict[str, str]:
    return dict(DARK)


def surface_for(widget: tk.Misc | None) -> dict[str, str]:
    if widget is None:
        return palette()
    try:
        root = widget.winfo_toplevel()
        stored = getattr(root, "_sparse_palette", None)
        if isinstance(stored, dict) and stored.get("bg"):
            return stored
    except Exception:
        pass
    return palette()


def zebra(index: int, widget: tk.Misc | None = None) -> str:
    c = surface_for(widget)
    return c["zebra0"] if index % 2 == 0 else c["zebra1"]


def apply_app_theme(root: tk.Misc) -> dict[str, str]:
    """Style default ttk widgets + tint common tk leaves. Returns active palette."""
    c = palette()
    try:
        root._sparse_palette = c  # type: ignore[attr-defined]
        root._bridge_palette = c  # type: ignore[attr-defined]
        root._bridge_ui_theme = "dark"  # type: ignore[attr-defined]
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    edge = {
        "background": c["bg"],
        "foreground": c["fg"],
        "borderwidth": 0,
        "relief": "flat",
        "lightcolor": c["bg"],
        "darkcolor": c["bg"],
        "bordercolor": c["bg"],
        "focuscolor": c["bg"],
    }
    style.configure(".", **edge)
    style.configure("TFrame", **edge)
    style.configure("TLabel", background=c["bg"], foreground=c["fg"], borderwidth=0)
    style.configure(
        "TCheckbutton",
        background=c["bg"],
        foreground=c["fg"],
        focuscolor=c["bg"],
        borderwidth=0,
        lightcolor=c["bg"],
        darkcolor=c["bg"],
        indicatorbackground=c["entry"],
        indicatorforeground=c["accent"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", c["bg"]), ("selected", c["bg"])],
        foreground=[("disabled", c["muted"]), ("active", c["fg"])],
    )
    style.configure(
        "TRadiobutton",
        background=c["bg"],
        foreground=c["fg"],
        focuscolor=c["bg"],
        borderwidth=0,
        lightcolor=c["bg"],
        darkcolor=c["bg"],
        indicatorbackground=c["entry"],
        indicatorforeground=c["accent"],
    )
    style.map(
        "TRadiobutton",
        background=[("active", c["bg"]), ("selected", c["bg"])],
        foreground=[("active", c["fg"]), ("selected", c["fg"])],
    )
    style.configure(
        "TButton",
        background=c["button"],
        foreground=c["fg"],
        borderwidth=0,
        focusthickness=0,
        focuscolor=c["button"],
        padding=(10, 4),
        relief="flat",
        lightcolor=c["button"],
        darkcolor=c["button"],
        bordercolor=c["button"],
    )
    style.map(
        "TButton",
        background=[("active", c["button_active"]), ("disabled", c["bg2"])],
        foreground=[("disabled", c["muted"])],
        relief=[("pressed", "flat"), ("!pressed", "flat")],
        lightcolor=[("active", c["button_active"])],
        darkcolor=[("active", c["button_active"])],
    )
    ib = c["input_border"]
    style.configure(
        "TEntry",
        fieldbackground=c["entry"],
        foreground=c["fg"],
        insertcolor=c["fg"],
        bordercolor=ib,
        lightcolor=ib,
        darkcolor=ib,
        padding=4,
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TEntry",
        fieldbackground=[("focus", c["entry"]), ("!focus", c["entry"])],
        foreground=[
            ("disabled", c["muted"]),
            ("focus", c["fg"]),
            ("!disabled", c["fg"]),
        ],
        bordercolor=[("focus", c["accent"])],
        lightcolor=[("focus", c["accent"])],
        darkcolor=[("focus", c["accent"])],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=c["entry"],
        foreground=c["fg"],
        background=c["button"],
        insertcolor=c["fg"],
        arrowcolor=c["fg"],
        bordercolor=ib,
        lightcolor=ib,
        darkcolor=ib,
        padding=4,
        borderwidth=1,
        relief="flat",
        arrowsize=11,
    )
    style.map(
        "TSpinbox",
        fieldbackground=[
            ("focus", c["entry"]),
            ("readonly", c["entry"]),
            ("!disabled", c["entry"]),
        ],
        foreground=[
            ("disabled", c["muted"]),
            ("readonly", c["fg"]),
            ("focus", c["fg"]),
            ("!disabled", c["fg"]),
        ],
        arrowcolor=[("disabled", c["muted"]), ("!disabled", c["fg"])],
        bordercolor=[("focus", c["accent"])],
        lightcolor=[("focus", c["accent"])],
        darkcolor=[("focus", c["accent"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=c["entry"],
        foreground=c["fg"],
        background=c["button"],
        arrowcolor=c["fg"],
        bordercolor=ib,
        lightcolor=ib,
        darkcolor=ib,
        padding=4,
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["entry"]), ("focus", c["entry"])],
        foreground=[
            ("disabled", c["muted"]),
            ("readonly", c["fg"]),
            ("!disabled", c["fg"]),
        ],
        arrowcolor=[("disabled", c["muted"])],
        bordercolor=[("focus", c["accent"])],
    )
    style.configure(
        "TLabelframe",
        background=c["bg"],
        foreground=c["muted"],
        bordercolor=c["bg2"],
        borderwidth=1,
        relief="flat",
        lightcolor=c["bg2"],
        darkcolor=c["bg2"],
    )
    style.configure(
        "TLabelframe.Label",
        background=c["bg"],
        foreground=c["muted"],
    )
    style.configure(
        "TNotebook",
        background=c["bg"],
        borderwidth=0,
        relief="flat",
        tabmargins=(2, 2, 2, 0),
        lightcolor=c["bg"],
        darkcolor=c["bg"],
        bordercolor=c["bg"],
    )
    style.configure(
        "TNotebook.Tab",
        background=c["tab"],
        foreground=c["muted"],
        padding=(12, 4),
        borderwidth=0,
        relief="flat",
        lightcolor=c["tab"],
        darkcolor=c["tab"],
        bordercolor=c["tab"],
        focuscolor=c["tab"],
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", c["tab_sel"]), ("active", c["hover"])],
        foreground=[("selected", c["fg"]), ("active", c["fg"])],
        lightcolor=[("selected", c["tab_sel"]), ("active", c["hover"])],
        darkcolor=[("selected", c["tab_sel"]), ("active", c["hover"])],
        bordercolor=[("selected", c["tab_sel"]), ("active", c["hover"])],
        expand=[("selected", [1, 1, 1, 0])],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=c["bg2"],
        troughcolor=c["bg"],
        bordercolor=c["bg"],
        arrowcolor=c["fg"],
        relief="flat",
        lightcolor=c["bg2"],
        darkcolor=c["bg2"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=c["bg2"],
        troughcolor=c["bg"],
        bordercolor=c["bg"],
        arrowcolor=c["fg"],
        relief="flat",
        lightcolor=c["bg2"],
        darkcolor=c["bg2"],
    )
    style.configure("TSeparator", background=c["bg2"])

    try:
        root.configure(bg=c["bg"])
    except Exception:
        pass

    install_entry_clipboard_class_bindings(root)
    _tint_tree(root, c)
    return c


def _tint_tree(widget: tk.Misc, c: dict[str, str]) -> None:
    try:
        cls = widget.winfo_class()
    except Exception:
        return
    try:
        if cls == "Canvas":
            widget.configure(  # type: ignore[call-arg]
                bg=c["canvas"],
                highlightthickness=0,
                bd=0,
                highlightbackground=c["canvas"],
            )
        elif cls == "Text":
            widget.configure(  # type: ignore[call-arg]
                bg=c["log_bg"],
                fg=c["fg"],
                insertbackground=c["fg"],
                selectbackground=c["select"],
                selectforeground=c["fg"],
                highlightthickness=0,
                bd=0,
                relief=tk.FLAT,
            )
        elif cls == "Listbox":
            widget.configure(  # type: ignore[call-arg]
                bg=c["entry"],
                fg=c["fg"],
                selectbackground=c["select"],
                selectforeground=c["fg"],
                highlightthickness=0,
                bd=0,
                relief=tk.FLAT,
            )
        elif cls == "Entry":
            widget.configure(  # type: ignore[call-arg]
                bg=c["entry"],
                fg=c["fg"],
                insertbackground=c["fg"],
                relief=tk.FLAT,
                highlightthickness=0,
                bd=0,
            )
        elif cls in ("Frame", "Labelframe", "Toplevel", "Tk"):
            try:
                widget.configure(  # type: ignore[call-arg]
                    bg=c["bg"],
                    highlightthickness=0,
                    highlightbackground=c["bg"],
                    bd=0,
                )
            except Exception:
                try:
                    widget.configure(bg=c["bg"])  # type: ignore[call-arg]
                except Exception:
                    pass
        elif cls == "Label":
            # Row labels manage their own zebra bg — skip if marked.
            if getattr(widget, "_sparse_row_tint", False):
                pass
            else:
                try:
                    widget.configure(  # type: ignore[call-arg]
                        bg=c["bg"],
                        fg=c["fg"],
                        highlightthickness=0,
                        highlightbackground=c["bg"],
                        bd=0,
                        relief=tk.FLAT,
                    )
                except Exception:
                    pass
        elif cls == "Button":
            if getattr(widget, "_sparse_custom_btn", False):
                pass
            else:
                try:
                    widget.configure(  # type: ignore[call-arg]
                        bg=c["button"],
                        fg=c["fg"],
                        activebackground=c["button_active"],
                        activeforeground=c["fg"],
                        relief=tk.FLAT,
                        bd=0,
                        highlightthickness=0,
                    )
                except Exception:
                    pass
        elif cls == "Checkbutton":
            if getattr(widget, "_sparse_row_tint", False):
                pass
            else:
                try:
                    widget.configure(  # type: ignore[call-arg]
                        bg=c["bg"],
                        fg=c["fg"],
                        activebackground=c["bg"],
                        activeforeground=c["fg"],
                        selectcolor=c["entry"],
                        highlightthickness=0,
                        bd=0,
                    )
                except Exception:
                    pass
    except Exception:
        pass

    try:
        kids = widget.winfo_children()
    except Exception:
        return
    for child in kids:
        _tint_tree(child, c)


def schedule_theme_refresh(root: tk.Misc, *, delay_ms: int = 60) -> None:
    try:
        root.after(delay_ms, lambda: apply_app_theme(root))
    except Exception:
        pass


def _is_under(widget: tk.Misc | None, ancestor: tk.Misc) -> bool:
    w: tk.Misc | None = widget
    while w is not None:
        if w == ancestor:
            return True
        try:
            w = w.master  # type: ignore[assignment]
        except Exception:
            return False
    return False


class RegionMousewheel:
    """Route MouseWheel to a canvas while the pointer is over its region."""

    _installed: set[int] = set()
    _regions: list[tuple[tk.Canvas, tk.Misc]] = []

    @classmethod
    def register(cls, root: tk.Misc, canvas: tk.Canvas, region: tk.Misc) -> None:
        cls._regions.append((canvas, region))
        rid = id(root)
        if rid in cls._installed:
            return
        cls._installed.add(rid)
        root.bind_all("<MouseWheel>", cls._on_wheel, add="+")
        root.bind_all("<Button-4>", cls._on_wheel, add="+")
        root.bind_all("<Button-5>", cls._on_wheel, add="+")

    @classmethod
    def _on_wheel(cls, event: tk.Event) -> str | None:
        try:
            under = event.widget.winfo_containing(event.x_root, event.y_root)
        except Exception:
            under = getattr(event, "widget", None)
        for canvas, region in list(cls._regions):
            try:
                if not canvas.winfo_exists():
                    continue
            except Exception:
                continue
            if not (_is_under(under, region) or _is_under(under, canvas)):
                continue
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(1, "units")
            return "break"
        return None


def style_on_off_button(btn: tk.Button, *, on: bool, colors: dict[str, str] | None = None) -> None:
    """Paint a compact On/Off toggle button."""
    c = colors or palette()
    btn._sparse_custom_btn = True  # type: ignore[attr-defined]
    if on:
        btn.configure(
            text="On",
            bg=c["on"],
            fg=c.get("on_fg", c["fg"]),
            activebackground=c["on_active"],
            activeforeground=c.get("on_fg", c["fg"]),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=2,
            cursor="hand2",
        )
    else:
        btn.configure(
            text="Off",
            bg=c["off"],
            fg=c["muted"],
            activebackground=c["off_active"],
            activeforeground=c["fg"],
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=2,
            cursor="hand2",
        )


def themed_spinbox(
    parent: tk.Misc,
    *,
    textvariable: tk.Variable,
    from_: int,
    to: int,
    width: int = 6,
    command: object | None = None,
) -> tk.Spinbox:
    """tk.Spinbox with dark chrome — ttk.Spinbox often draws blank under clam."""
    c = surface_for(parent)
    kwargs: dict = {
        "from_": from_,
        "to": to,
        "width": width,
        "textvariable": textvariable,
        "bg": c["entry"],
        "fg": c["fg"],
        "insertbackground": c["fg"],
        "buttonbackground": c["button"],
        "relief": tk.FLAT,
        "bd": 1,
        "highlightthickness": 1,
        "highlightbackground": c["input_border"],
        "highlightcolor": c["accent"],
        "buttonuprelief": tk.FLAT,
        "buttondownrelief": tk.FLAT,
        "font": ("Segoe UI", 10),
    }
    if command is not None:
        kwargs["command"] = command
    sb = tk.Spinbox(parent, **kwargs)
    sb._sparse_custom_btn = True  # type: ignore[attr-defined]
    bind_entry_clipboard(sb)
    return sb


def bind_entry_clipboard(entry: ttk.Entry | tk.Entry | tk.Spinbox) -> None:
    """Restore Ctrl+X/C/V/A on Windows (clam ttk.Entry drops them)."""

    def _cut(_event=None):
        try:
            if entry.selection_present():
                chunk = entry.selection_get()
                entry.clipboard_clear()
                entry.clipboard_append(chunk)
                entry.delete("sel.first", "sel.last")
        except Exception:
            try:
                entry.event_generate("<<Cut>>")
            except Exception:
                pass
        return "break"

    def _copy(_event=None):
        try:
            if entry.selection_present():
                chunk = entry.selection_get()
                entry.clipboard_clear()
                entry.clipboard_append(chunk)
        except Exception:
            try:
                entry.event_generate("<<Copy>>")
            except Exception:
                pass
        return "break"

    def _paste(_event=None):
        # Do not rely on <<Paste>> — clam ttk.Entry often no-ops it silently.
        try:
            text = entry.clipboard_get()
        except Exception:
            return "break"
        if not text:
            return "break"
        try:
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
        except Exception:
            pass
        try:
            entry.insert(tk.INSERT, text)
        except Exception:
            try:
                entry.insert("insert", text)
            except Exception:
                pass
        return "break"

    def _select_all(_event=None):
        try:
            entry.selection_range(0, tk.END)
            entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    for seq, handler in (
        ("<Control-x>", _cut),
        ("<Control-X>", _cut),
        ("<Control-c>", _copy),
        ("<Control-C>", _copy),
        ("<Control-v>", _paste),
        ("<Control-V>", _paste),
        ("<Control-Key-v>", _paste),
        ("<Control-Key-V>", _paste),
        ("<Control-a>", _select_all),
        ("<Control-A>", _select_all),
    ):
        entry.bind(seq, handler)


def _clipboard_target(event: tk.Event) -> tk.Misc | None:
    w = getattr(event, "widget", None)
    if w is None:
        return None
    try:
        cls = w.winfo_class()
    except Exception:
        return None
    if cls in ("TEntry", "Entry", "Spinbox", "TSpinbox"):
        return w
    return None


def _class_cut(event: tk.Event) -> str | None:
    entry = _clipboard_target(event)
    if entry is None:
        return None
    try:
        if entry.selection_present():  # type: ignore[attr-defined]
            chunk = entry.selection_get()  # type: ignore[attr-defined]
            entry.clipboard_clear()
            entry.clipboard_append(chunk)
            entry.delete("sel.first", "sel.last")  # type: ignore[attr-defined]
    except Exception:
        pass
    return "break"


def _class_copy(event: tk.Event) -> str | None:
    entry = _clipboard_target(event)
    if entry is None:
        return None
    try:
        if entry.selection_present():  # type: ignore[attr-defined]
            chunk = entry.selection_get()  # type: ignore[attr-defined]
            entry.clipboard_clear()
            entry.clipboard_append(chunk)
    except Exception:
        pass
    return "break"


def _class_paste(event: tk.Event) -> str | None:
    entry = _clipboard_target(event)
    if entry is None:
        return None
    try:
        text = entry.clipboard_get()
    except Exception:
        return "break"
    if not text:
        return "break"
    try:
        if entry.selection_present():  # type: ignore[attr-defined]
            entry.delete("sel.first", "sel.last")  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        entry.insert(tk.INSERT, text)  # type: ignore[attr-defined]
    except Exception:
        try:
            entry.insert("insert", text)  # type: ignore[attr-defined]
        except Exception:
            pass
    return "break"


def _class_select_all(event: tk.Event) -> str | None:
    entry = _clipboard_target(event)
    if entry is None:
        return None
    try:
        entry.selection_range(0, tk.END)  # type: ignore[attr-defined]
        entry.icursor(tk.END)  # type: ignore[attr-defined]
    except Exception:
        pass
    return "break"


def install_entry_clipboard_class_bindings(root: tk.Misc) -> None:
    """Class-level Ctrl+X/C/V/A so every Entry keeps paste under clam."""
    if getattr(root, "_sparse_entry_clipboard_installed", False):
        return
    try:
        root._sparse_entry_clipboard_installed = True  # type: ignore[attr-defined]
    except Exception:
        pass
    for cls in ("TEntry", "Entry", "Spinbox", "TSpinbox"):
        for seq, handler in (
            ("<Control-x>", _class_cut),
            ("<Control-X>", _class_cut),
            ("<Control-c>", _class_copy),
            ("<Control-C>", _class_copy),
            ("<Control-v>", _class_paste),
            ("<Control-V>", _class_paste),
            ("<Control-Key-v>", _class_paste),
            ("<Control-Key-V>", _class_paste),
            ("<Control-a>", _class_select_all),
            ("<Control-A>", _class_select_all),
        ):
            try:
                root.bind_class(cls, seq, handler)
            except Exception:
                pass


def bind_text_clipboard(text: tk.Text) -> None:
    """Restore Ctrl+X/C/V/A in multiline text widgets."""

    def _cut(_event=None):
        try:
            if text.tag_ranges(tk.SEL):
                chunk = text.get(tk.SEL_FIRST, tk.SEL_LAST)
                text.clipboard_clear()
                text.clipboard_append(chunk)
                text.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except Exception:
            pass
        return "break"

    def _copy(_event=None):
        try:
            if text.tag_ranges(tk.SEL):
                chunk = text.get(tk.SEL_FIRST, tk.SEL_LAST)
                text.clipboard_clear()
                text.clipboard_append(chunk)
        except Exception:
            pass
        return "break"

    def _paste(_event=None):
        try:
            chunk = text.clipboard_get()
        except Exception:
            return "break"
        try:
            if text.tag_ranges(tk.SEL):
                text.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except Exception:
            pass
        try:
            text.insert(tk.INSERT, chunk)
        except Exception:
            pass
        return "break"

    def _select_all(_event=None):
        try:
            text.tag_add(tk.SEL, "1.0", tk.END)
            text.mark_set(tk.INSERT, tk.END)
            text.see(tk.INSERT)
        except Exception:
            pass
        return "break"

    for seq, handler in (
        ("<Control-x>", _cut),
        ("<Control-X>", _cut),
        ("<Control-c>", _copy),
        ("<Control-C>", _copy),
        ("<Control-v>", _paste),
        ("<Control-V>", _paste),
        ("<Control-Key-v>", _paste),
        ("<Control-Key-V>", _paste),
        ("<Control-a>", _select_all),
        ("<Control-A>", _select_all),
    ):
        text.bind(seq, handler)

