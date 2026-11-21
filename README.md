# Paper Lanterns website

The new site for [Paper Lanterns](https://paperlanterns.inc): whole collections of public-domain letters,
typed exactly as printed and set beside the scanned page they came from. It is a sister project of
[Akshara](https://akshara.ink).

This repository holds **design only**: Hugo templates, one stylesheet, one small script and fonts. Every
word and number about a book comes from the Paper Lanterns pipeline (`../Paper Lanterns New`), which
writes Hugo content; a thin script copies it here. Scans are not stored here: pages load them from the
Internet Archive.

Status: all 39 compiled editions are in (5,017 letters), plus the old site's 105 hand-curated letters, essays,
lectures, speeches and notes at their old addresses. Nothing is deployed yet.

## What is where

| Path | What it holds |
| --- | --- |
| `content/_index.md`, `content/collections/_index.md` | Site copy for the home and collections pages |
| `content/collections/<book_id>/` | Synced from the pipeline. Do not edit by hand. |
| `static/collections/<book_id>/` | The book's EPUB, Markdown and TEI downloads, synced from the pipeline |
| `content/{letters,essays,lectures,speeches,garden,sets}/` | Hand-curated pages from the old site, copied verbatim by `scripts/import_legacy.py` (do not edit by hand; edit at the source and re-import) |
| `legacy-addresses.txt` | The 128 addresses the old site served; each stays in `published-addresses.txt` for good |
| `layouts/` | Templates: `index.html` (home), `collections/list.html`, `collections/book.html`, `collections/letter.html` |
| `assets/css/site.css`, `assets/js/site.js` | All styling and all interactivity (the pages read fully without the script) |
| `static/fonts/` | Self-hosted Newsreader and IBM Plex Mono (SIL Open Font Licence, files included) |
| `scripts/sync_from_pipeline.py` | Copies one book from the pipeline, checking every SHA-256 |
| `scripts/check_site.py` | Checks the built pages: structure, links, ids, CSP hazards, JSON-LD |
| `published-addresses.txt`, `scripts/addresses.py` | Every address the site has served; `verify` fails if one stops working without a redirect in `static/_redirects` |
| `scripts/check_mobile.mjs` | Opens the built pages in headless Chromium at 360, 390 and 768 px; fails on sideways scroll, small touch targets or small letter text |
| `verify` | The one command that says whether the site is fit to publish |

## Run it

You need gitleaks 8.30.1 (`.gitleaks-version`), Pagefind 1.6.0 (`.pagefind-version`), Hugo **0.139.3 extended** (pinned in `.hugo-version`), Python 3.12+, Node 22+ and Chromium or Chrome
(for the phone-width check; set `CHROME=/path/to/browser` if it is not in a standard place).

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

The sync replaces the book's folders wholesale, so a letter removed upstream disappears here too. Then record any new
addresses and commit both:

```bash
hugo --destination /tmp/pl-build && python3 scripts/addresses.py update /tmp/pl-build
```

The site must build without the pipeline present (CI and the host have only this repository). Letter
addresses are numbers (`/collections/<book_id>/<n>/`) and are frozen once published (DECISIONS.md D12).

## Check it

```bash
./verify
```

It checks the Hugo version, scans the git history for secrets, parses the script, runs the script tests, confirms the synced content still
matches the pipeline output, builds the site with warnings as errors, checks every built page, holds the
JavaScript budget (50 KB), opens the key pages at phone and tablet widths in headless Chromium, and finally
runs the pipeline's own `./verify`. `./verify --skip-pipeline` leaves
out the pipeline (CI does this, since the pipeline repository is not public).

## Deploy

Not set up yet. The plan (DECISIONS.md D2) is Cloudflare Pages building from this repository with
`hugo --gc --minify && pagefind --site public` (search index, D17); `public/_headers` carries the
Content-Security-Policy and security headers and `public/_redirects` the old-site redirects.

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
