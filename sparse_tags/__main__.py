"""Entry point: python -m sparse_tags"""

from __future__ import annotations

from sparse_tags.bootstrap import apply_env


def main() -> None:
    apply_env()
    # Reload CFG after env so Danbooru auth is available.
    try:
        import bot.core.config as cfg_mod

        cfg_mod.CFG = cfg_mod.Config.load()
    except Exception:
        pass
    from sparse_tags.gui import SparseTagBrowser

    SparseTagBrowser().mainloop()


if __name__ == "__main__":
    main()
