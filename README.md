# Paper Lanterns website

The new site for [Paper Lanterns](https://paperlanterns.inc): whole collections of public-domain letters,
typed exactly as printed and set beside the scanned page they came from. It is a sister project of
[Akshara](https://akshara.ink).

This repository holds **design only**: Hugo templates, one stylesheet, one small script and fonts. Every
word and number about a book comes from the Paper Lanterns pipeline (`../Paper Lanterns New`), which
writes Hugo content; a thin script copies it here. Scans are not stored here: pages load them from the
Internet Archive.

Status: walking skeleton. One book is in (`dostoevsky-family-friends-1914`). Nothing is deployed yet.

## What is where

| Path | What it holds |
| --- | --- |
| `content/_index.md`, `content/collections/_index.md` | Site copy for the home and collections pages |
| `content/collections/<book_id>/` | Synced from the pipeline. Do not edit by hand. |
| `static/collections/<book_id>/` | The book's EPUB, Markdown and TEI downloads, synced from the pipeline |
| `layouts/` | Templates: `index.html` (home), `collections/list.html`, `collections/book.html`, `collections/letter.html` |
| `assets/css/site.css`, `assets/js/site.js` | All styling and all interactivity (the pages read fully without the script) |
| `static/fonts/` | Self-hosted Newsreader and IBM Plex Mono (SIL Open Font Licence, files included) |
| `scripts/sync_from_pipeline.py` | Copies one book from the pipeline, checking every SHA-256 |
| `scripts/check_site.py` | Checks the built pages: structure, links, ids, CSP hazards |
| `verify` | The one command that says whether the site is fit to publish |

## Run it

You need Hugo **0.139.3 extended** (pinned in `.hugo-version`), Python 3.12+ and Node (only for a syntax check).

```bash
hugo server
```

Then open http://localhost:1313/. The home page, `/collections/dostoevsky-family-friends-1914/` and
`/collections/dostoevsky-family-friends-1914/letter-0020-f-dostoevsky/` (letter XX) are the three designed pages.

## Add or refresh a book

In the pipeline repository, render the Hugo content for a compiled edition, then copy it here:

```bash
cd "../Paper Lanterns New" && uv run lanterns render-hugo dostoevsky-family-friends-1914
```

```bash
python3 scripts/sync_from_pipeline.py dostoevsky-family-friends-1914
```

The sync replaces the book's folders wholesale, so a letter removed upstream disappears here too. Commit the
result: the site must build without the pipeline present (CI and the host have only this repository).

## Check it

```bash
./verify
```

It checks the Hugo version, parses the script, runs the script tests, confirms the synced content still
matches the pipeline output, builds the site with warnings as errors, checks every built page, holds the
JavaScript budget (50 KB), and finally runs the pipeline's own `./verify`. `./verify --skip-pipeline` leaves
out the pipeline (CI does this, since the pipeline repository is not public).

## Deploy

Not set up yet. The plan (DECISIONS.md D2) is Cloudflare Pages building `hugo --gc --minify` from this
repository; `public/_headers` carries the Content-Security-Policy and security headers.

## Licence

Not chosen yet (see DECISIONS.md, open questions). The letters are in the public domain; the site's footer
states that transcriptions are CC BY 4.0, the owner's default for content. The fonts are under the SIL Open
Font Licence (`static/fonts/OFL-*.txt`).
