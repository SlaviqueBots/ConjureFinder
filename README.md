# Conjure Finder

Find the cheapest bot `/conjure` (or `/conjure_hell`) command for a Danbooru or Rule34 post.

## Download (share this)

1. Open the latest **[GitHub Release](../../releases/latest)**.
2. Download **`ConjureFinder-v*-windows.exe`**.
3. Put it in any folder and run it.
4. Open **Settings…** and paste your API keys (saved beside the exe as `conjure_finder.env` — never share that file).

No Python install needed for the `.exe`.

### Get API keys

- Danbooru: https://danbooru.donmai.us/api_keys  
- Rule34: https://rule34.xxx/index.php?page=account&s=options  
  (Generate New Key → Save → copy `api_key` and `user_id`)

## Tips

- Also considers roster paths: conjure character → reshape (solo) / reshape_m (−solo), or conjure artist → Author. Rule34 uses the same solo split plus rating / −ai filters; AI posts use `/conjure_hell_slop`.
- Sparse general tags may be cheaper via `/beckon` / `/beckon_hell` (cost 30, up to 10 peeks) than repeated conjures.
- Paste one or more post URLs (one per line). Danbooru and Rule34 queues run in parallel.
- Frozen builds can auto-update from an optional release server (`CHECK_UPDATES` / `UPDATE_*` in env).

## Develop from source

Requirements: Windows, [Python 3](https://www.python.org/downloads/) with **Add to PATH** and **tcl/tk**.

```text
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
python -m conjure_finder
```

Or double-click **`Conjure Finder.vbs`** (fallback: `Conjure Finder.bat`).

### Build a shareable exe locally

```text
python scripts/build_conjure_finder_exe.py
```

Outputs `releases/ConjureFinder-vX.Y.Z-windows.exe` (plus `.sha256`).

### Cut a GitHub Release

1. Bump `__version__` in `conjure_finder/__init__.py`.
2. Commit and push to `main`.
3. Tag and push:

```text
git tag v1.0.5
git push origin v1.0.5
```

GitHub Actions builds the Windows exe and attaches it to the release automatically.
