# Conjure Finder

> 100% vibecoded — no hand-written code.

Desktop GUI that finds the cheapest `/conjure` path for a Danbooru or Rule34 post. Read-only: it never modifies the bot.

## Run

Needs Python 3 with Tkinter (`pip install -r requirements.txt`), then:

```bash
python -m conjure_finder
```

Paste post URLs — one per line for separate jobs, space-separated on one line for an any-of group (variants, same-author sets). Copy the resulting command(s) into the bot chat. **Bulk wishlist** mode ranks paths across many posts of one character/artist, with save/load for results.

## API keys

Danbooru username + API key and Rule34 key + user id go in **Settings…** inside the app (stored locally, never in this repo).

## How it searches

- Pricing mirrors the bot: regular tags 25, character/title/author tags 50, one free reroll.
- Considers `/beckon` peeks on sparse tags, roster paths (conjure artist → Author, conjure character → reshape), and targeted excludes.
- Cheapest-first; stops at the first guaranteed path per job.
