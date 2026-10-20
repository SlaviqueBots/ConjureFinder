"""Clean tkinter UI for the resonance FE/hour quick check."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from tl_resonance import __version__
from tl_resonance.calc import (
    NR_DROP_AMOUNT,
    NR_DROP_CHANCE,
    PERK_DS_DUPLICATE,
    PERK_ERASE,
    PERK_TO_DS,
    Inputs,
    calculate,
)


def _fmt_fe(v: float) -> str:
    if abs(v) >= 100:
        return f"{v:,.1f}"
    if abs(v) >= 10:
        return f"{v:,.2f}"
    return f"{v:,.3f}"


class ResonanceCalc(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"TL Resonance Calc  v{__version__}")
        self.minsize(420, 540)
        self.geometry("460x560")
        self.resizable(False, False)

        self._nr = tk.StringVar(value="0.12")
        self._ds = tk.StringVar(value="3")
        self._bosses = tk.StringVar(value="1")
        self._duration = tk.StringVar(value="3")

        for var in (self._nr, self._ds, self._bosses, self._duration):
            var.trace_add("write", lambda *_: self._recalc())

        self._build()
        self._recalc()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill=tk.BOTH, expand=True)

        prices = ttk.LabelFrame(root, text="Market prices (FE)", padding=10)
        prices.pack(fill=tk.X, pady=(0, 8))
        self._row(prices, "Netherrealm resonance", self._nr, "FE each")
        self._row(prices, "Deep Space resonance", self._ds, "FE each")

        farming = ttk.LabelFrame(root, text="Farming pace", padding=10)
        farming.pack(fill=tk.X, pady=(0, 8))
        self._row(farming, "Bosses per map", self._bosses, "")
        self._row(farming, "Avg map duration", self._duration, "min")

        drop = ttk.LabelFrame(root, text="Fixed drop", padding=10)
        drop.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            drop,
            text=(
                f"{NR_DROP_CHANCE * 100:g}% chance for {NR_DROP_AMOUNT} "
                "Netherrealm resonances per boss kill"
            ),
            wraplength=400,
        ).pack(anchor=tk.W)

        perk = ttk.LabelFrame(root, text="Perk package (all or nothing)", padding=10)
        perk.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            perk,
            text=(
                f"{PERK_TO_DS * 100:g}% convert NR → Deep Space\n"
                f"{PERK_ERASE * 100:g}% of remaining NR erased\n"
                f"{PERK_DS_DUPLICATE * 100:g}% chance to duplicate resulting Deep Space"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        out = ttk.LabelFrame(root, text="Expected value / hour", padding=10)
        out.pack(fill=tk.BOTH, expand=True)

        self._wo_lbl = ttk.Label(out, text="Without perks: —", font=("", 11))
        self._wo_lbl.pack(anchor=tk.W, pady=2)
        self._w_lbl = ttk.Label(out, text="With perks: —", font=("", 11))
        self._w_lbl.pack(anchor=tk.W, pady=2)

        ttk.Separator(out, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        self._delta_lbl = ttk.Label(out, text="Difference: —", font=("", 12, "bold"))
        self._delta_lbl.pack(anchor=tk.W, pady=2)
        self._verdict_lbl = ttk.Label(out, text="", foreground="#333")
        self._verdict_lbl.pack(anchor=tk.W, pady=(4, 0))

        self._err_lbl = ttk.Label(out, text="", foreground="#a33")
        self._err_lbl.pack(anchor=tk.W, pady=(8, 0))

        hint = ttk.Label(
            root,
            text="Values update as you type. Positive difference = take the perks.",
            foreground="#666",
            font=("", 8),
        )
        hint.pack(anchor=tk.W, pady=(6, 0))

    def _row(
        self, parent: ttk.LabelFrame, label: str, var: tk.StringVar, unit: str
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=26, anchor=tk.W).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, width=10, justify=tk.RIGHT)
        entry.pack(side=tk.LEFT, padx=(4, 4))
        if unit:
            ttk.Label(row, text=unit, width=8, anchor=tk.W).pack(side=tk.LEFT)

    def _parse(self) -> Inputs:
        return Inputs(
            nr_price_fe=float(self._nr.get().strip()),
            ds_price_fe=float(self._ds.get().strip()),
            bosses_per_map=float(self._bosses.get().strip()),
            map_duration_min=float(self._duration.get().strip()),
        )

    def _recalc(self) -> None:
        try:
            result = calculate(self._parse())
        except (ValueError, TypeError) as exc:
            self._err_lbl.configure(text=str(exc) or "Enter valid numbers.")
            self._wo_lbl.configure(text="Without perks: —")
            self._w_lbl.configure(text="With perks: —")
            self._delta_lbl.configure(text="Difference: —")
            self._verdict_lbl.configure(text="")
            return

        self._err_lbl.configure(text="")
        self._wo_lbl.configure(
            text=f"Without perks:  {_fmt_fe(result.fe_per_hour_without)} FE / hour"
        )
        self._w_lbl.configure(
            text=f"With perks:       {_fmt_fe(result.fe_per_hour_with)} FE / hour"
        )
        delta = result.delta_fe_per_hour
        sign = "+" if delta > 0 else ""
        self._delta_lbl.configure(
            text=f"Difference:  {sign}{_fmt_fe(delta)} FE / hour"
        )
        if abs(delta) < 1e-9:
            verdict = "Perks break even at these prices."
            color = "#555"
        elif delta > 0:
            verdict = "Take the perk package — net gain vs baseline."
            color = "#1a7a3a"
        else:
            verdict = "Skip the perk package — net loss vs baseline."
            color = "#a33"
        self._verdict_lbl.configure(text=verdict, foreground=color)


def main() -> None:
    ResonanceCalc().mainloop()


if __name__ == "__main__":
    main()
