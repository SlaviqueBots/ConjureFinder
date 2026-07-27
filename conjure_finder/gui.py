"""Simple tkinter GUI for the conjure finder (English UI)."""

from __future__ import annotations

import asyncio
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from conjure_finder import __version__
from conjure_finder.urls import split_url_jobs


def _format_elapsed(sec: float) -> str:
    if sec < 10:
        return f"{sec:.1f}s"
    if sec < 60:
        return f"{sec:.0f}s"
    m, s = divmod(int(sec), 60)
    return f"{m}m{s:02d}s"


def _format_result(index: int, total: int, result: Any) -> str:
    """Compact one-block summary (no notes / warnings section)."""
    ids = tuple(getattr(result, "post_ids", None) or ()) or (result.post_id,)
    id_part = "|".join(f"#{i}" for i in ids)
    head = f"[{index}/{total}] {result.source} {id_part}"
    if len(ids) > 1:
        head += f"  any-of {len(ids)}"
    if result.file_ext:
        head += f"  .{result.file_ext}"
    head += f"  tags={result.tags_on_post}  checked={result.checked}"
    elapsed = getattr(result, "elapsed_sec", 0) or 0
    if elapsed > 0:
        head += f"  in {_format_elapsed(elapsed)}"
    if not result.best:
        return head + "\n  (no usable conjure option)\n"
    opt = result.best
    g = "YES" if opt.guaranteed else "no"
    path = getattr(opt, "path", "conjure") or "conjure"
    lines = [head]
    for cmd_line in (opt.command or "").splitlines():
        lines.append(f"  {cmd_line}")
    lines.append(
        f"  path {path}  cost {opt.cost}  pool {opt.pool_size}  guarantee {g}  "
        f"~{opt.expected_sessions:.1f} steps / ~{opt.expected_currency:.0f} cur"
    )
    return "\n".join(lines) + "\n"


def _format_error(index: int, total: int, label: str, message: str) -> str:
    short = label if len(label) <= 72 else label[:69] + "…"
    return f"[{index}/{total}] ERROR  {short}\n  {message}\n"


class ConjureFinderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Conjure Finder  v{__version__}")
        self.minsize(680, 520)
        self.geometry("760x600")

        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._last_commands: list[str] = []
        self._update_busy = False

        self._build()
        self._install_clipboard_bindings()
        from conjure_finder.updater import load_update_config

        if load_update_config().check_updates:
            self.after(1500, lambda: self.check_updates(silent=True))

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            root,
            text=(
                "Post URLs — one per line = separate searches; "
                "same line (space or |) = any-of group"
            ),
        ).pack(anchor=tk.W)

        url_frame = ttk.Frame(root)
        url_frame.pack(fill=tk.BOTH, **pad)
        self.url_text = tk.Text(url_frame, height=5, wrap=tk.WORD, font=("Consolas", 10))
        self.url_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        url_scroll = ttk.Scrollbar(url_frame, command=self.url_text.yview)
        url_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.url_text.configure(yscrollcommand=url_scroll.set)
        self.url_text.bind("<Control-Return>", lambda _e: self.start_search())

        btn_row = ttk.Frame(root)
        btn_row.pack(fill=tk.X, **pad)
        self.find_btn = ttk.Button(btn_row, text="Find cheapest conjure", command=self.start_search)
        self.find_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(
            btn_row, text="Cancel", command=self.cancel_search, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.settings_btn = ttk.Button(btn_row, text="Settings…", command=self.open_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.update_btn = ttk.Button(
            btn_row, text="Check for updates", command=lambda: self.check_updates(silent=False)
        )
        self.update_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.copy_btn = ttk.Button(
            btn_row, text="Copy command(s)", command=self.copy_command, state=tk.DISABLED
        )
        self.copy_btn.pack(side=tk.RIGHT)

        ttk.Label(root, text="Status").pack(anchor=tk.W)
        self.status_var = tk.StringVar(value="Paste one or more post URLs and click Find.")
        self.status_text = tk.Text(
            root, height=2, wrap=tk.WORD, font=("Segoe UI", 9), relief=tk.FLAT, borderwidth=0
        )
        self.status_text.pack(anchor=tk.W, fill=tk.X, pady=(2, 0))
        self.status_text.insert("1.0", self.status_var.get())
        self.status_text.configure(state=tk.DISABLED)
        self.status_var.trace_add("write", self._sync_status_text)

        ttk.Label(root, text="Result").pack(anchor=tk.W, pady=(10, 0))
        self.result = tk.Text(root, height=18, wrap=tk.WORD, font=("Consolas", 10))
        self.result.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.result.configure(state=tk.DISABLED)

    def _sync_status_text(self, *_args: object) -> None:
        text = self.status_var.get()
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", text)
        self.status_text.configure(state=tk.DISABLED)

    def _install_clipboard_bindings(self) -> None:
        from conjure_finder.clipboard_bindings import install_clipboard_bindings

        install_clipboard_bindings(self.url_text, self.result, self.status_text)

    def _set_result(self, text: str) -> None:
        self.result.configure(state=tk.NORMAL)
        self.result.delete("1.0", tk.END)
        self.result.insert(tk.END, text)
        self.result.configure(state=tk.DISABLED)

    def _append_result(self, text: str) -> None:
        self.result.configure(state=tk.NORMAL)
        self.result.insert(tk.END, text)
        self.result.see(tk.END)
        self.result.configure(state=tk.DISABLED)

    def start_search(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        jobs = split_url_jobs(self.url_text.get("1.0", "end"))
        if not jobs:
            messagebox.showinfo(
                "Conjure Finder",
                "Paste one or more Danbooru / Rule34 post URLs first.\n\n"
                "Tip: put related variants on the same line for an any-of search.",
            )
            return
        self._cancel.clear()
        self._last_commands = []
        self.copy_btn.configure(state=tk.DISABLED)
        self.find_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        n_urls = sum(len(j) for j in jobs)
        any_of = sum(1 for j in jobs if len(j) > 1)
        if any_of:
            self.status_var.set(
                f"Queued {len(jobs)} job(s) ({n_urls} URLs, {any_of} any-of)…"
            )
        else:
            self.status_var.set(f"Queued {len(jobs)} URL(s)…")
        self._set_result("")
        self._worker = threading.Thread(target=self._run_worker, args=(jobs,), daemon=True)
        self._worker.start()

    def open_settings(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo(
                "Conjure Finder",
                "Wait for the current search to finish (or cancel it) before changing keys.",
            )
            return
        from conjure_finder.settings_ui import SettingsDialog

        SettingsDialog(self)

    def cancel_search(self) -> None:
        self._cancel.set()
        self.status_var.set("Cancelling…")

    def copy_command(self) -> None:
        if not self._last_commands:
            return
        text = "\n".join(self._last_commands)
        self.clipboard_clear()
        self.clipboard_append(text)
        n = len(self._last_commands)
        self.status_var.set(f"Copied {n} command(s).")

    def _run_worker(self, jobs: list[list[str]]) -> None:
        from conjure_finder.batch import run_batch

        site_status: dict[str, str] = {}

        def on_progress(site: str, msg: str) -> None:
            site_status[site] = msg

            def _update() -> None:
                parts = [f"{s}: {m}" for s, m in site_status.items() if m]
                self.status_var.set(" | ".join(parts) if parts else msg)

            self.after(0, _update)

        def on_item_done(index: int, total: int, label: str, payload: Any) -> None:
            if isinstance(payload, Exception):
                block = _format_error(index, total, label, str(payload))
            else:
                block = _format_result(index, total, payload)
                if payload.best:
                    self._last_commands.append(payload.best.command)
            self.after(0, lambda b=block: self._append_result(b + "\n"))

        try:
            asyncio.run(
                run_batch(
                    jobs,
                    progress=on_progress,
                    cancel_check=self._cancel.is_set,
                    on_item_done=on_item_done,
                )
            )
        except Exception as exc:
            self.after(0, lambda: self._on_error(str(exc)))
            return
        self.after(0, self._on_batch_done)

    def _on_error(self, message: str) -> None:
        self.find_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        self.status_var.set("Error.")
        self._append_result(f"Error:\n{message}\n")
        messagebox.showerror("Conjure Finder", message)

    def _on_batch_done(self) -> None:
        self.find_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        if self._last_commands:
            self.copy_btn.configure(state=tk.NORMAL)
            self.status_var.set(f"Done. {len(self._last_commands)} command(s) ready to copy.")
        elif self._cancel.is_set():
            self.status_var.set("Cancelled.")
        else:
            self.status_var.set("Done.")

    def check_updates(self, *, silent: bool = False) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        threading.Thread(
            target=self._check_updates_thread, args=(silent,), daemon=True
        ).start()

    def _check_updates_thread(self, silent: bool) -> None:
        from conjure_finder.updater import check_for_update, load_update_config

        try:
            info = check_for_update(load_update_config())
        except Exception as exc:
            self._update_busy = False
            if not silent:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Conjure Finder", f"Update check failed:\n{exc}"
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
                            "Conjure Finder",
                            f"You're on the latest version (v{__version__}).",
                        ),
                    ),
                )
            return

        def _ask() -> None:
            ok = messagebox.askyesno(
                "Conjure Finder",
                f"Version {info.version} is available (you have {__version__}).\n\n"
                "Download and install now?\n\n"
                "The app will close. After that, start Conjure Finder.exe yourself "
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
        from conjure_finder.updater import load_update_config, run_update

        try:
            run_update(load_update_config(), info)
        except Exception as exc:
            self._update_busy = False
            self.after(
                0,
                lambda: (
                    self.status_var.set(f"Update failed: {exc}"),
                    messagebox.showerror("Conjure Finder", f"Update failed:\n{exc}"),
                ),
            )
            return
        if getattr(sys, "frozen", False):

            def _done() -> None:
                self.status_var.set(f"Installed v{info.version} — start again.")
                messagebox.showinfo(
                    "Conjure Finder",
                    f"Version {info.version} is ready.\n\n"
                    "This window will close. Then double-click Conjure Finder.exe "
                    "in the folder that opens (or use your usual shortcut).",
                )
                self.after(400, self.destroy)

            self.after(0, _done)
        else:
            self._update_busy = False
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Conjure Finder",
                    f"Downloaded v{info.version} (dev mode — not applying).",
                ),
            )


def main() -> None:
    app = ConjureFinderApp()
    app.mainloop()
