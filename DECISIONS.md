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
  where the slug is the pipeline's `LetterUnit.slug` (superseded by D12: letters are numbered). The 88 curated letters of the old site keep
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

## D8. Phones are the primary target; checked by a headless browser (2026-11-21)

- **Decision:** The stylesheet is written mobile-first: base rules for a ~360px phone, `min-width` queries at
  600, 761 and 901px. On phones the header is a menu button, covers sit two per row, charts scroll sideways
  inside their own box with a "Swipe sideways" hint, and the book title comes before the frontispiece. On the
  letter page phones get one column, text first; the scan is a separate view reached from a bottom bar
  (Contents, Page/Text, Aa, Next) or by tapping a passage, which opens the page with those lines lit and
  scrolled into view; "Back to the text" returns to the passage. Reading text is at least 18px on phones;
  buttons and block links are at least 44px tall; nothing depends on hover. Scans use width-based `srcset`
  (642w/1283w) with `sizes`, lazy-loaded below the fold. `scripts/check_mobile.mjs` drives Chromium headless
  over its DevTools protocol (Node built-ins only, network to other hosts blocked) at 360, 390 and 768px and
  fails `verify` on sideways page scroll, touch targets under 44px or letter text under 18px.
- **Why:** The owner wants the whole design as phone-friendly as possible; a machine check keeps it that way.
- **Rejected:** Playwright or Puppeteer (large dependency trees for one check); side-by-side text and scan on
  phones (both become unreadable at 360px).

## D9. Licences: MIT for code, CC BY 4.0 for content (2026-11-21)

- **Decision:** The owner's words: "MIT for code, CC BY 4 for letters". Code in this repository and in the
  pipeline is MIT (`LICENSE`). Transcriptions, compiled editions, synced content and data are CC BY 4.0
  (`LICENSE-CONTENT`, with the official legal code and a suggested credit line). The letters themselves are in
  the public domain; the licence covers the transcription and its apparatus. The footer reads
  "Transcriptions CC BY 4.0. Code MIT." and each letter's structured data carries the licence URL.
- **Why:** Free reuse with credit, so copies lead back to the edition and its scans.
- **Rejected:** CC0 for content (briefly chosen as "most permissive", then corrected by the owner the same day).

## D10. The old site's essays, lectures and speeches move here at their current addresses (2026-11-21)

- **Decision:** When the old Astro site is retired, its essays, lectures and speeches pages move to this site
  and keep the URLs they have today. Not migrated yet (a later phase); until then nothing on this site may take
  those addresses.
- **Why:** Old links keep working; nothing published is lost.

## D11. Public repositories; secrets kept out by gitleaks (2026-11-21)

- **Decision:** This repository and the pipeline will be public. Keys live only in `.env` (ignored, with
  `.env.example` as the one tracked template) or a host secret store. gitleaks 8.30.1, pinned in
  `.gitleaks-version` and checksum-verified in CI, runs as a pre-commit hook (`.githooks/pre-commit`, refuses the
  commit on any finding), over the whole history in `./verify`, and in CI on every push. `SECURITY.md` says
  what to do if a key leaks. The full history of both repositories was scanned before this decision: no leaks.
- **Why:** The owner's first worry about going public is leaked keys.
- **Rejected:** Scanning the working tree (`gitleaks dir`): it would read the ignored local `.env` that holds real
  keys in the pipeline folder; the staged-changes hook covers new files instead.

## D12. Letter addresses are numbers, frozen once published; a ledger guards them (2026-11-21)

- **Decision:** Supersedes the slug part of D3. A book's letters live at `/collections/<book_id>/<n>/`, where `n`
  is the letter's sequence number in the edition without padding (letter XX of the Dostoevsky volume is
  `/collections/dostoevsky-family-friends-1914/20/`). Curated letters keep `/letter/<slug>/`. Numbers are frozen
  once published. `published-addresses.txt` lists every page and download address the site serves and only ever
  grows (`scripts/addresses.py update`); `./verify` fails if a listed address is no longer served and has no
  redirect in `static/_redirects`, if a redirect points nowhere, or if a served address is missing from the
  ledger. Each letter also carries the pipeline's `stable_id` (its first printed block, e.g. `p0079-b0002`), so if
  a later re-split renumbers letters, old numbers can be mapped to new ones and redirected.
- **Why:** The owner asked for "whatever is cleaner". Short, readable, citable addresses; the ledger makes
  "never break a link" a machine check instead of a promise.
- **Rejected:** Pipeline slugs such as `letter-0020-f-dostoevsky` (long, and they change when sender metadata
  improves); zero-padded numbers.

## D13. Titles: the printed heading on the page, metadata titles for search (2026-11-21)

- **Decision:** The owner asked for both archival fidelity and search; they are kept in separate places.
  - On the page: no invented titles. A small kicker gives the printed heading as printed ("XX · To his Brother
    Michael"); the headline is the letter's own opening words, cut at the first sentence end, else a clause
    break, within about 90 characters, with an ellipsis if cut. Curated letters will keep their hand-written titles.
  - In `<title>`, Open Graph and Twitter tags: "Sender to recipient, date written out · Paper Lanterns", from
    metadata with full names from the pipeline's `edition.toml` (e.g. "Fyodor Dostoevsky to his brother Michael,
    22 December 1849"), falling back to "Sender, date", "Letter to recipient" or "Letter" when parts are missing.
  - Meta description: the opening words, up to about 155 characters.
  - schema.org JSON-LD: a `Message` on each letter (author, recipient, dateCreated, locationCreated, licence,
    url, and `isPartOf` the `Book` with translator, publisher, 1914 publication and the Internet Archive scan),
    a `Book` on each collection page, a `WebSite` on the home page. `check_site.py` fails if any block does not
    parse. Canonical links on every page; Hugo writes `sitemap.xml`.
- **Why:** Readers see only what the printer printed; search engines get clear, accurate metadata.
- **Rejected:** Hand-written editorial titles for book letters (invented text on the page).

## D14. The whole library is in; pages degrade cleanly when data is missing (2026-11-21)

- **Decision:** All 39 compiled editions (5,017 letters) are synced. Rules that keep large or uneven books readable:
  - A book with no Internet Archive item (today only `vivekananda-letters-1944`, made from a PDF elsewhere) shows
    no scan views, no "light it on the page" hint and no scan images; it says so in plain words.
    `check_site.py` fails on any archive.org address with an empty item id.
  - Generated covers use the frontispiece, else the title page, and draw the page strip from the pipeline's
    run-length `page_runs` (one rectangle per run, not per page): the home page fell from 836 KB to 80 KB.
  - The home page shows the seven largest volumes; the collections page groups every volume by collection,
    in order of publication.
  - The home page's opening salutations are 24 distinct ones from dated letters, spread evenly across the
    library's timeline, keeping only text that is short and ends in punctuation (longer text in that field is a
    pipeline misreading of the letter's first words).
  - Year charts space their ticks by span (5, 10, 50 or 100 years) and compress stroke stacks so the busiest year
    stays within the chart; the decade chart thins its labels as decades multiply.
  - Synced content is rendered from the pipeline's committed code, not from uncommitted work in its folder.
- **Why:** Every book must read well without hand-tuning; missing data must look intentional, never broken.
- **Size:** about 47 MB of pages and 57 MB of downloads in this repository; the largest file is 2 MB.

## D15. The old site's hand-curated content moves here at its own addresses (2026-11-21)

- **Decision:** `scripts/import_legacy.py` copies the old Astro site's published Markdown (87 letters, 10 essays,
  5 lectures, 2 speeches, 1 garden note, 6 curated sets) into `content/{letters,essays,lectures,speeches,garden,sets}/`
  verbatim, so hand-written titles, sources, context and links are exactly as published. Hugo permalinks keep
  `/letter/<file>/`, `/essay/<file>/`, `/lecture/<file>/`, `/speech/<file>/`, `/garden/<file>/` and
  `/collection/<file>/`, with list pages at `/letters/`, `/essays/`, `/lectures/`, `/speeches/` and `/garden/`.
  `verify` fails if the copy drifts from the old repository (when that folder is present). Deliberate exceptions:
  - not migrated: `aristotle-alexander-335bc.md.disabled` (never published) and garden notes marked private;
  - raw HTML poem blocks and `<h5>` headings in Thoreau's "Walking" become Markdown verse with hard line breaks
    and a `{.poem}` class (same 12,500 words in the same order), because this site renders no raw HTML; any
    other raw HTML stops the import;
  - dates such as `62-01-01` (Seneca), which the old site showed as 1962, are padded to `0062-01-01` and shown
    as "AD 62". A date on 1 January is shown as the year alone, since that is how the old site recorded a year
    with no known day.
  - The old themes (`src/content/themes/`) are byte-identical to the six sets and were never served (404 on the
    live site), so they are not migrated separately.
- Each curated page says plainly that it was chosen and transcribed from the named source and has not yet been
  set beside a scan, unlike the collections. YouTube recordings are linked, never embedded (no third-party frames).
- **Why:** Old links keep working and the owner's curation survives unchanged.
- **Open:** the old site's own verification report (45 letters) predates many of the 87 now live; see open questions.

## D16. Every old-site address resolves; old endpoints and the service worker are handled (2026-11-21)

- **Decision:** `legacy-addresses.txt` lists the 128 addresses the old site served: the 123 in its live sitemap
  (paperlanterns.ink, read 2026-11-21) plus `/rss.xml`, `/search-data.json`, `/api/random-content.json`,
  `/sw.js` and `/manifest.json`. All are in the published-address ledger, and `addresses.py check` fails if
  any leaves it. Served here: every content page, `/letters/`, `/essays/`, `/lectures/`, `/speeches/`,
  `/garden/`, `/collections/` (which now also lists the six curated sets), `/about/` (the owner's own About text
  kept word for word, its outdated figures replaced by live counts and a short factual section on the
  collections), `/rss.xml` (books and curated pages), and the two JSON endpoints in their old shapes.
  Redirected (301): `/archive/` to `/letters/`; `/admin/`, `/command/` and `/offline/` to `/`. `/sw.js` is a
  replacement service worker that deletes the old site's caches and unregisters itself, so returning visitors
  are not stuck on cached old pages. `check_site.py` also fails if the feed is not well-formed XML or a JSON
  endpoint does not parse.
- **Why:** The owner's rule: no published link may break.

## D17. Search with Pagefind: a static index built at deploy, one CSP allowance (2026-11-21)

- **Decision:** Pagefind 1.6.0 (CloudCannon; a single Rust binary, the standard search tool for static sites,
  MIT licence, released 2026-11-01) indexes the built site after Hugo runs. Version pinned in `.pagefind-version`;
  CI downloads the official release and checks its SHA-256. Only reading text is indexed: collection letters
  (with their printed headings), the hand-curated pages and each book's introduction (`data-pagefind-body`),
  with page furniture marked `data-pagefind-ignore`. `/search/` uses Pagefind's JavaScript API with our own
  results list built from text nodes (excerpt highlights copied as `<mark>` elements, nothing inserted as HTML),
  loaded only on that page. The CSP gains exactly one allowance, `'wasm-unsafe-eval'`, which Pagefind's
  WebAssembly needs; scripts, data and styles still come only from this site.
- **Why the platform is not enough:** a static site has no server to search on, and a hand-rolled JSON index
  of 5,000 letters would be several megabytes per visit; Pagefind fetches only the few small chunks a query needs.
- **Size:** about 33 MB of index chunks; about 10,700 files in the whole built site (Cloudflare Pages allows
  20,000; `verify` fails above 19,000). The search page works only with JavaScript and says so.
- **Rejected:** Pagefind's own UI (writes HTML strings and styles); a hosted search service (third party, cost).

## D18. People and Explore are generated from the content, never typed by hand (2026-11-21)

- **Decision:** `scripts/build_indexes.py` derives `data/decades.json` (every decade with a dated letter and its
  letters) and `data/people.json` from the synced collections and the hand-curated pages; Hugo content adapters
  (`content/explore/_content.gotmpl`, `content/people/_content.gotmpl`) turn them into `/explore/<decade>s/`
  (51 pages, first-century decades labelled "AD") and `/people/<name>/` (103 pages). `verify` fails if the
  files are stale.
- People are listed as the data records them, not as inferred writers: everyone credited on a volume with the role
  exactly as recorded ("tr.", "ed."; "named on the title page" when there is none), the writers named on the
  hand-curated pages, and counts of collection letters only where the signed name (or the pipeline's
  edition.toml full form) equals a credited name exactly. So the East India Company appears as credited on its
  six volumes, and anthology contributors appear only where a signature matches.
- `data/people-same-person.json` joins printed forms of one person (today only Gandhi's three forms); a pair is
  added only when certain.
- The decade chart links each decade to its Explore page. People and Explore addresses are recorded in the ledger
  like any other.
- **Rejected:** guessing writers from book titles or matching names loosely (would publish wrong attributions).

## D19. Design refinements from the owner's review: header, menu, covers, decade chart (2026-11-21)

- **Header:** six links (Collections, Letters, Essays, People, Explore, About); the logo is the way home and
  search is an icon beside the menu button. The full row shows only from 1100px, where it fits on one line;
  nothing in the header may wrap. `check_mobile.mjs` now also runs at 935 and 1280px and fails if the logo or a
  header link wraps.
- **Menu:** a full-screen reading sheet instead of a dropdown: a search field first, then each destination in
  large Newsreader with a line of real figures (volumes, letters, decades), the current page marked with the
  lamp dot. Built on `<details>`, so it works without JavaScript; with it, the page behind stops scrolling and
  Escape closes it.
- **Covers carry no scans.** Cropped scan plates could not be controlled per book (portraits on some, a sliver of
  title-page type or blank paper on others, poor contrast). Each cover is now typographic: collection tint and
  accent, title and writer, and the shape of the book itself drawn from its page strip (tall where letters are
  printed, middling for the editor's pages, short for front matter and index), as fine page hairlines. Scans stay
  where they are seen whole: framed on the book page and beside each letter.
- **Decade chart:** long silences (more than four empty decades) fold into a short `//` break labelled with its
  dates, so the crowded centuries get the width; the chosen lantern glows with a halo and shows its count; century
  labels are italic serif; scrollbars are thin, and the chart scrolls sideways only below 720px.
- **Why:** the owner's review: "Why does the header suck?", "Looks boring and lazy?", covers "out of contrast,
  clipped", "How do we design this to be more beautiful?"

## D20. Cover system and book-page order (2026-11-21)

- **Covers** (supersedes the cover paragraph of D19): typographic, no scans, three axes of real difference.
  - Colour follows the era of the letters (the weighted middle year): parchment and umber before 1600, madder
    for the 1600s, sage for the 1700s, cornflower for 1800-1849, lavender for 1850-1899, slate teal after 1900,
    grey when undated. The collection is a small italic label, no longer the colour.
  - Layout follows the credits: one writer named on the title page makes their name the hero; two make a pair
    joined by the site's two-lantern string (Sand and Flaubert, Nietzsche and Wagner, Faraday and Schoenbein);
    anthologies credited only to editors or compilers make the title the hero.
  - The picture is the book's own lanterns: one per decade of dated letters on a sagging string, longer where more
    letters survive, the busiest lit. A miniature of the site's decade chart, true for every book.
- **Book page order:** title, figures and "Read the first letter", then the letters straight away (grouped by the
  writer's life periods where the book has them, otherwise by decade, with jump links and two-line openings), then
  the year chart, page strip, downloads and colophon. Before, readers met three charts and the downloads before
  learning the letters could be read.
- **Why:** the owner's review: covers lacked style and looked the same; the book page buried the letters.

## D21. The header steps aside while you read (2026-11-21)

- **Decision:** on every page except letter pages, the header hides while you scroll down past the first screenful
  and slides back on any scroll up, with a hairline and slight translucency; never hidden while the menu is open;
  no motion for readers who ask for reduced motion; without JavaScript it simply stays at the top. Letter pages keep
  their own toolbar and, on phones, the bottom reading bar instead.
- **Why:** a permanently sticky header costs about a tenth of a phone screen on every scroll; a static one strands
  readers at the bottom of 400-letter books.

## D22. Book pages are built around the letters (2026-11-21)

- **Decision** (supersedes the book-page order in D20): a title band in the book's era colour with its lanterns, a
  one-sentence description assembled only from data ("434 letters of Tipu Sultan, written between 1785 and 1811,
  translated by William Kirkpatrick, printed in 1811…"), "Read the first letter", "Browse all letters" and a one-line
  download list; then the first letter as a showcase; then the letters, with tabs (life periods or decades) that
  stay in reach and underline the group on screen; then one "About this edition" section holding the colophon,
  the frontispiece and title-page plates, figures, year chart, page strip with a printed-style contents list keyed
  to it, the files, and the checking stages. Letter rows are set like the head of a small letter: date and place,
  the opening words upright with a lamp-red hanging quote, then the printed number and recipient.
- **Why:** the owner's review asked for the page to be redesigned around reading, with beauty, elegance and
  refinement as the measure.

## D23. The address is paperlanterns.ink (2026-11-21)

- **Decision:** `baseURL`, canonical links, the sitemap, structured data and the credit line use
  `https://paperlanterns.ink/`, the domain the old site already lives on, so the new site replaces it in place.
- **Rejected:** paperlanterns.inc, which was a typo and does not resolve.

## D24. Every book shows its reading score and says plainly that a machine read it (2026-11-21)

- **Decision:** the pipeline's 100-point rubric score travels into each book's front matter (`quality`: score, each
  pillar with its maximum, places flagged). Book pages show it as a seal under the title ("Read by machine. Not yet
  proofread by people. Expect a few slips.") linking to a "How this text was read" section in About this edition: what
  a vision language model is, the five parts of the score, the proofreading stages, and an invitation to Akshara's
  community. Every letter page repeats the status in one line under "How it was read". `/reading/` lists what
  machine reading tends to get wrong, in any book and in letters especially, and how the score is worked out.
  `check_site` fails any book page without exactly one score between 0 and 100. "Typed exactly as printed" became
  "read by machine", because typing implied a person had done it.
- **Why:** the owner wants readers to know the text is a machine reading with a low but real error rate, without it
  reading as an alarm, and to see that proofreading is open to volunteers. The tone is a note, not a warning: no
  warning colours or icons.
- **Rejected:** a banner on every letter (it would shout over the letters); hiding the score in the colophon only
  (the owner asked for it to be prominent).

## D25. The old collections subdomain redirects as a whole, not page by page (2026-11-21)

- **Decision:** when the Astro sites are shut down, `collections.paperlanterns.ink` gets one Cloudflare redirect
  rule sending every address to `https://paperlanterns.ink/collections/`. The main domain keeps its page-by-page
  redirects (`static/_redirects`), which already exist and cost nothing.
- **Why:** the owner is letting the old subdomain go. Its collections are being digitized afresh (three are already
  on the site; Glimpses of Bengal and Nehru's Letters from a Father to His Daughter are listed in the pipeline's
  `config/wishlist-additions.json`), so its 256 letter addresses have no exact new homes. One rule keeps old links
  and search results from ending in an error.
- **Rejected:** 256 individual redirects (no reliable one-to-one mapping, upkeep for little gain); no redirect at
  all (every old link breaks).

## D26. Deploy by uploading a checked build; Cloudflare builds nothing (2026-11-21)

- **Decision:** the site goes live by `wrangler pages deploy` of a folder built and checked on the owner's machine
  (`./verify`, then `hugo --gc --minify` and the pinned, checksum-checked Pagefind). The Pages project
  `paper-lanterns-site` is a direct-upload project, not connected to GitHub. The old collections subdomain is moved
  to a three-line redirect Worker kept in `ops/collections-redirect/`, because Wrangler's login can manage Workers
  domains but not zone redirect rules. Hashed scripts and stylesheets get a year-long immutable cache.
- **Why:** the pre-launch security review pointed out that Cloudflare's build machines do not ship Pagefind, so a
  Cloudflare build would fetch an unpinned package on every deploy. Uploading the build that passed `verify` keeps
  every dependency pinned and checked.
- **Rejected:** a Cloudflare Git build (unpinned Pagefind); deploying from GitHub Actions (needs a Cloudflare API
  token stored as a GitHub secret; worth doing later, with the owner's agreement, so deploys do not depend on one
  laptop).

## D27. The site runs as a Worker serving static files, not a Pages project (2026-11-21)

- **Decision:** `wrangler deploy` uploads the checked `dist/` folder to the Worker `paper-lanterns-site`, which has no
  code of its own (`[assets]` only, `html_handling = "auto-trailing-slash"`, `not_found_handling = "404-page"`).
  `_headers` and `_redirects` work the same way. This replaces the direct-upload Pages project in D26; the rest of
  D26 (Cloudflare builds nothing, deploys use the pinned Pagefind) still holds.
- **Why:** the owner's choice: Workers is where Cloudflare is putting its effort, and the old collections subdomain
  already runs as one. Tested before launch: all pages, all 128 old addresses, headers, the 404 page and search
  behave exactly as on Pages.
- **Rejected:** keeping the Pages project.

## D28. Launch: paperlanterns.ink moved to the Worker (2026-11-21)

- **What changed:** the two CNAME records for `paperlanterns.ink` and `www` (to `paper-lanterns.pages.dev`) were
  deleted with the `cf` CLI and both hostnames attached to the `paper-lanterns-site` Worker as custom domains, which
  recreates their DNS; both were then detached from the old `paper-lanterns` Pages project. The zone route
  `collections.paperlanterns.ink/*` and that hostname's custom domain now point at
  `paper-lanterns-collections-redirect`. The site Worker's workers.dev address is off.
- **Checked live:** all 128 old addresses resolve to a page, security headers present, 404 page returns 404, old
  subdomain answers 301 to `/collections/`.
- **To undo:** recreate the two CNAMEs to `paper-lanterns.pages.dev` (after removing the Worker custom domains),
  re-add the domains to the `paper-lanterns` Pages project, and point the route back at `paper-lanterns-collections`.
- **Left in place on purpose:** the old Pages project, the old collections Worker and the unused
  `paper-lanterns-site` Pages project from D26, until the owner agrees to delete them.

## Open questions for the owner

1. **Curated letters' authenticity.** The old site's verification report covers 45 letters; 87 are live now. Should
   the ones added after that report be re-checked before launch?
2. **People.** People pages list everyone as the books credit them. Do you want writers curated per volume
   (for example, separating the East India Company, which received its letters, from the factors who wrote them)?
3. **Akshara community link.** The notice links to https://akshara.ink/. Is there a page for joining the community or
   proofreading that it should point to instead?
