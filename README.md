# Paper Lanterns website

The new site for [Paper Lanterns](https://paperlanterns.ink): whole collections of public-domain letters,
read from the printed page by machine and set beside the scanned page they came from. It is a sister project of
[Akshara](https://akshara.ink).

This repository holds **design only**: Hugo templates, one stylesheet, one small script and fonts. Every
word and number about a book comes from the Paper Lanterns pipeline (code at
[bebhuvan/paper-lanterns-pipeline](https://github.com/bebhuvan/paper-lanterns-pipeline); checked out locally
as `../Paper Lanterns New`, which also holds the compiled editions), which writes Hugo content; a thin script copies it here. Scans are not stored here: pages load them from the
Internet Archive.

Status: live at https://paperlanterns.ink since 21 November 2026. All 39 compiled editions are in (5,017
letters), plus the old site's 105 hand-curated letters, essays, lectures, speeches and notes at their old addresses.

## What is where

| Path | What it holds |
| --- | --- |
| `content/_index.md`, `content/collections/_index.md` | Site copy for the home and collections pages |
| `content/collections/<book_id>/` | Synced from the pipeline. Do not edit by hand. |
| `static/collections/<book_id>/` | The book's EPUB, Markdown and TEI downloads, synced from the pipeline |
| `content/{letters,essays,lectures,speeches,garden,sets}/` | Hand-curated pages from the old site, copied verbatim by `scripts/import_legacy.py` (do not edit by hand; edit at the source and re-import) |
| `content/journal/<slug>/index.md` | Journal posts, written here by hand (D32). A `cover.*` file and any pictures sit beside the post |
| `legacy-addresses.txt` | The 128 addresses the old site served; each stays in `published-addresses.txt` for good |
| `layouts/` | Templates: `index.html` (home), `collections/list.html`, `collections/book.html`, `collections/letter.html` |
| `assets/css/site.css`, `assets/js/site.js` | All styling and all interactivity (the pages read fully without the script) |
| `static/fonts/` | Self-hosted Newsreader and IBM Plex Mono (SIL Open Font Licence, files included) |
| `scripts/sync_from_pipeline.py` | Copies one book from the pipeline, checking every SHA-256 |
| `scripts/build_indexes.py`, `data/` | People and Explore indexes derived from the content (`data/people-same-person.json` is the one hand-kept list) |
| `scripts/check_site.py` | Checks the built pages: structure, links, ids, CSP hazards, JSON-LD |
| `published-addresses.txt`, `scripts/addresses.py` | Every address the site has served; `verify` fails if one stops working without a redirect in `static/_redirects` |
| `scripts/og_cards.mjs`, `scripts/png_palette.mjs` | Draw the 1200×630 share cards (Open Graph images) from Hugo's `card.html` pages in headless Chromium (D31) |
| `scripts/fetch_plates.py`, `assets/og/plates/` | Each book's frontispiece plate for its share card, fetched once from the Internet Archive |
| `scripts/check_mobile.mjs` | Opens the built pages in headless Chromium at 360, 390 and 768 px; fails on sideways scroll, small touch targets or small letter text |
| `verify` | The one command that says whether the site is fit to publish |

## Run it

You need gitleaks 8.30.1 (`.gitleaks-version`), Pagefind 1.6.0 (`.pagefind-version`), Hugo **0.139.3 extended** (pinned in `.hugo-version`), Python 3.12+, Node 22+ and Chromium or Chrome
(for the phone-width check and the share cards; set `CHROME=/path/to/browser` if it is not in a standard place).

```bash
hugo server
```

Then open http://localhost:1313/. The home page, `/collections/dostoevsky-family-friends-1914/` and
`/collections/dostoevsky-family-friends-1914/20/` (letter XX) are the three designed pages.

## Add or refresh a book

To refresh every book, loop over the committed editions in the pipeline (`git ls-files 'library/*/edition_manifest.json'`)
and run the two commands below for each.

In the pipeline repository, render the Hugo content for a compiled edition, then copy it here:

```bash
cd "../Paper Lanterns New" && uv run lanterns render-hugo dostoevsky-family-friends-1914
```

```bash
python3 scripts/sync_from_pipeline.py dostoevsky-family-friends-1914
```

The sync replaces the book's folders wholesale, so a letter removed upstream disappears here too. If the book has a
frontispiece, fetch its plate for the share card (the only step that uses the network; `verify` fails until it is done):

```bash
python3 scripts/fetch_plates.py
```

Then rebuild the People and Explore indexes, record any new addresses, and commit:

```bash
python3 scripts/build_indexes.py
```


```bash
hugo --destination /tmp/pl-build && python3 scripts/addresses.py update /tmp/pl-build
```

The site must build without the pipeline present (CI and the host have only this repository). Letter
addresses are numbers (`/collections/<book_id>/<n>/`) and are frozen once published (DECISIONS.md D12).

## Write a journal post

Make a folder `content/journal/<slug>/` with an `index.md` that starts like this:

```yaml
---
title: "The title"
subtitle: "An optional line under it"
date: 2026-11-22
author: Bhuvan
slug: the-title
description: "One sentence. It is the summary in link previews, and the line under the title when there is no subtitle."
---
```

Then write in Markdown. Leave out a `# Title` line (the title comes from the front matter above; a single `#` stops the build). `## Heading` opens a numbered section (a number you type, like `I.` or `2.`, is dropped, since the page numbers sections itself) and `### Heading` a smaller one; `> quote` is a quotation, and a last line in it
starting with `— ` (`— Thoreau, *Walking*, 1862`) becomes its source; a quotation followed by a line `{.pull}` is
a pull quote; `[^1]` makes a note, shown in the margin beside its paragraph (a note cited from a list, quotation or heading goes in a Notes list at the end instead); `![alt text](picture.jpg "Caption")` places a picture saved in
the same folder. For a cover, save `cover.jpg` in the folder and add `cover:` with `alt`, `credit`, `licence`, and
optionally `caption` and `source_url`; the build stops if any of the first three is missing. `featured: true` puts a
post at the top of the journal page instead of the newest one. Add the new address with
`python3 scripts/addresses.py update <built dir>` and commit it with the post. For the first post, also add its address to `PAGES` in `scripts/check_mobile.mjs`, so `verify` checks a post page at phone width.

## Check it

```bash
./verify
```

It checks the Hugo version, scans the git history for secrets, parses the script, runs the script tests, confirms the synced content still
matches the pipeline output, builds the site with warnings as errors, draws the share cards, checks every built page
(including that each names a 1200×630 share card that exists), holds the
JavaScript budget (50 KB), opens the key pages at phone and tablet widths in headless Chromium, and finally
runs the pipeline's own `./verify`. `./verify --skip-pipeline` leaves
out the pipeline (CI does this, since the pipeline repository is not public).

## Deploy

A Cloudflare Worker named `paper-lanterns-site` that serves only static files (D27; config in `wrangler.toml`).
Cloudflare builds nothing: build and check locally, then upload the checked folder:

```bash
./verify
rm -rf dist && hugo --gc --minify --destination dist && node scripts/og_cards.mjs dist && pagefind --site dist
wrangler deploy
```

Drawing all 5,057 share cards from nothing takes about four minutes; they are cached in `.cache/og/` (not committed),
so later builds draw only the cards whose page changed. A card whose text cannot be fitted stops the build, and an
image of it is saved in `.cache/og/failed/`.

`dist/_headers` carries the Content-Security-Policy and security headers and `dist/_redirects` the old-site
redirects; Workers static assets apply both.

The launch on 21 November 2026 (D25, D28) attached `paperlanterns.ink` and `www.paperlanterns.ink` to the Worker as
custom domains, after deleting their old DNS records that pointed at the `paper-lanterns` Pages project, and
pointed the old `collections.paperlanterns.ink` route and domain at the redirect Worker in `ops/collections-redirect/`.
The old `paper-lanterns` Pages project and `paper-lanterns-collections` Worker still exist, detached, so the switch
can be undone; delete them once the new site has run cleanly for a while.

Search does not work under `hugo server` (the index is built after Hugo). To try it locally, build with the
command above and serve `public/` with any static server.

## Licence

- Code (templates, styles, scripts): MIT, see `LICENSE`.
- Transcriptions, synced content and data: CC BY 4.0, see `LICENSE-CONTENT`. The letters themselves are public-domain works.
- Fonts: SIL Open Font Licence (`static/fonts/OFL-*.txt`).

## Secrets

The site needs no keys. Anything secret goes in `.env` (ignored) or the host's secret store, never in git.
gitleaks scans every commit (pre-commit hook) and the whole history (`./verify`, CI). Enable the hook once per
clone with `git config core.hooksPath .githooks`; you need gitleaks 8.30.1 (`.gitleaks-version`). See `SECURITY.md`.
