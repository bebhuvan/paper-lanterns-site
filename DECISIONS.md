# Decisions

Numbered and append-only. Each says what was decided, why, and what was rejected. Read before changing
how the site is built; say why if you overturn one.

## D1. Hugo, pinned to 0.139.3 extended (2026-11-21)

- **Decision:** Build the site with Hugo, the same tool as Akshara. Pin the version in `.hugo-version`;
  `./verify` refuses any other version and CI installs exactly that release after checking its SHA-256.
  Use 0.139.3 because it is what is installed and it has everything this site uses (JSON front matter,
  Hugo Pipes for minify and fingerprint, custom output formats); nothing newer is needed yet.
- **Why:** One static generator across sister projects; a single binary with no package tree to audit.
- **Rejected:** Keeping the old Astro site (a second toolchain and a large dependency tree); upgrading Hugo
  without a reason.

## D2. Static output, Cloudflare Pages, scans from the Internet Archive (2026-11-21)

- **Decision:** Static files only. Host on Cloudflare Pages (not set up yet). Page scans are loaded straight
  from Internet Archive BookReader URLs, `https://archive.org/download/<id>/page/n<leaf>_w<width>.jpg`,
  where `leaf` is the 0-based scan leaf (pipeline decision D20). Pages ask for width 600, with 1200 for
  sharp screens; the Archive serves 642 and 1283 pixels for these.
- **Why:** No server, no database, nothing to hack and nothing to pay for; the scans already live at a
  durable public home.
- **Rejected:** Copying scans into this repository or a bucket (gigabytes, and a second copy to keep right).

## D3. Address scheme (2026-11-21)

- **Decision:** Books at `/collections/<book_id>/`; a book's letters at `/collections/<book_id>/<letter-slug>/`,
  where the slug is the pipeline's `LetterUnit.slug`. The 88 curated letters of the old site keep
  `/letter/<slug>/` when they move (not done yet). Downloads sit beside the book page:
  `/collections/<book_id>/<book_id>.epub` and so on.
- **Why:** Book ids are already the pipeline's stable identifiers; keeping the old letter URLs keeps old links alive.
- **Open:** pipeline slugs include a sender fragment (`letter-0020-f-dostoevsky`); if the pipeline ever changes
  a slug, the old URL must redirect. See open questions.

## D4. The site holds design; content comes from the pipeline (2026-11-21)

- **Decision:** The pipeline's `lanterns render-hugo <book_id>` (pipeline D23) writes JSON-front-matter Hugo
  pages and a `manifest.json`. `scripts/sync_from_pipeline.py` copies exactly what the manifest lists, checks
  every SHA-256, and replaces the book folders wholesale. Pages go to `content/collections/<book_id>/`;
  downloads go to `static/collections/<book_id>/` because Hugo would treat the book's Markdown file as a page
  if it sat in `content/`. Synced content is committed so the site builds without the pipeline;
  `./verify` fails if the committed copy drifts from the pipeline output.
- **Why:** Akshara's render-then-sync split. One owner per fact: if a number on a page is wrong, the fix is in
  the pipeline, never in a template.
- **Rejected:** Templates reading the pipeline's `collection_ast.json` directly (8 MB per book, and couples the
  site to the compiler's internal schema); a symlink to the pipeline folder (breaks CI and hosting).

## D5. Editorial periods are cited book data, not site data (2026-11-21)

- **Decision:** The life periods that group letters on a book page (Petersburg, The Fortress, …) live in the
  pipeline's `books/<id>/book.toml` as `[[life_periods]]`, each with a `source`. For Dostoevsky they come from
  the book's own Chronological Table (printed pp. xi–xvi). A book without periods lists its letters in printed
  order.
- **Why:** No invented data on the site; every label traces to a page someone can check.
- **Rejected:** A hand-kept periods file in this repository (content in the design repo).

## D6. No raw HTML from data; strict CSP; JavaScript only as enhancement (2026-11-21)

- **Decision:** Letter text arrives as runs (`{t, c, tag, fn}`) and the templates escape every run; Goldmark's
  `unsafe` stays off. The Content-Security-Policy allows scripts, styles and fonts only from this site and
  images only from this site and `archive.org`; no inline scripts, styles or `style=""` attributes, so charts
  are SVG with geometry in attributes and the lit passage on a scan is an SVG rectangle in the page's
  0–1000 bbox space. The policy has one owner (`params.security.csp` in `hugo.toml`), written to
  Cloudflare's `_headers` by `layouts/index.headers`; `scripts/check_site.py` fails if the dev-server copy
  drifts. One script, `assets/js/site.js` (about 7 KB minified), adds the interactive parts; every page
  reads fully without it.
- **Why:** The owner's security baseline; content from outside is data, never markup.
- **Rejected:** Pre-rendered HTML in Markdown bodies; inline style positions for charts; a JS framework.

## D7. Fonts self-hosted; no runtime dependencies; checks in the standard library (2026-11-21)

- **Decision:** Newsreader 400/400 italic/500 and IBM Plex Mono 400, latin and latin-ext subsets, copied from
  Fontsource 5.3.0 (`@fontsource/newsreader`, `@fontsource/ibm-plex-mono`, SIL OFL 1.1, licence files in
  `static/fonts/`). The sync and check scripts and their tests use only the Python standard library; the only
  external tools are Hugo itself and Node for `node --check`.
- **Why:** No calls to Google Fonts (privacy, CSP); nothing to install, update or audit beyond Hugo.
- **Rejected:** html-validate, htmltest or lychee as dependencies for the skeleton (each is another toolchain;
  `check_site.py` covers the mistakes this site can make). A full W3C validator may be worth adding later.

## Open questions for the owner

1. Licence for the site's code (MIT or Apache-2.0 are the defaults) and confirmation that transcriptions are CC BY 4.0.
2. Whether the old site's essays, lectures, speeches, garden, themes and collections pages move here, and at what addresses.
3. GitHub remotes: this repository and the pipeline repository have none; public or private?
4. Letter titles: the design shows editorial titles ("Not more than a minute to live"); the pipeline has none,
   so pages use the printed heading ("XX · To his Brother Michael"). Write titles (by hand, cited) or keep headings?
5. Pipeline slugs (`letter-0020-f-dostoevsky`) become permanent URLs; keep them, or switch to number-based slugs before launch?
