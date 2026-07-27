"""Entry point: python -m conjure_finder"""

from __future__ import annotations

from conjure_finder.bootstrap import ensure_path, load_env


def main() -> None:
    ensure_path()
    load_env()
    from conjure_finder.settings import apply_settings_file, settings_status

    apply_settings_file()
    from conjure_finder.gui import ConjureFinderApp

    app = ConjureFinderApp()
    st = settings_status()
    if not (st["danbooru"] or st["rule34"]):
        app.after(
            300,
            lambda: app.status_var.set(
                "No API keys found — open Settings… to add Danbooru / Rule34 credentials."
            ),
        )
    app.mainloop()


if __name__ == "__main__":
    main()
