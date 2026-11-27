"""Tests for scripts/check_site.py and scripts/sync_from_pipeline.py. Standard library only; no network."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import addresses  # noqa: E402
import build_indexes  # noqa: E402
import import_legacy  # noqa: E402
import check_site  # noqa: E402
import ping_indexnow  # noqa: E402
import sync_from_pipeline as sync  # noqa: E402

CSP = "default-src 'none'; img-src 'self' https://archive.org"
HUGO_TOML = f'''
[params.security]
  csp = "{CSP}"
[[server.headers]]
  for = "/**"
  [server.headers.values]
    Content-Security-Policy = "{CSP}"
'''
OG = (
    '<meta property="og:image" content="https://paperlanterns.ink/card.png"><meta property="og:image:width" content="1200">'
    '<meta property="og:image:height" content="630"><meta property="og:image:alt" content="a">'
    '<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="https://paperlanterns.ink/card.png">'
)
GOOD = """<!doctype html><html lang="en"><head><title>T</title><meta name="description" content="d">""" + OG + """</head>
<body><h1 id="top">Hi</h1><p><a href="/other/">o</a> <a href="#top">t</a> <img src="https://archive.org/x.jpg" alt=""></p>
<svg viewBox="0 0 1 1"><rect x="0" y="0" width="1" height="1"/></svg></body></html>"""


def write_site(root: Path, index_html: str) -> Path:
    public = root / "public"
    (public / "other").mkdir(parents=True)
    (public / "index.html").write_text(index_html, encoding="utf-8")
    (public / "other" / "index.html").write_text(GOOD.replace('href="/other/"', 'href="/"'), encoding="utf-8")
    (public / "_headers").write_text(f"/*\n  Content-Security-Policy: {CSP}\n", encoding="utf-8")
    (public / "card.png").write_bytes(png_header(1200, 630))
    (root / "hugo.toml").write_text(HUGO_TOML, encoding="utf-8")
    return public


def png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x03\x00\x00\x00"


class CheckSiteTests(unittest.TestCase):
    def problems(self, html: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            public = write_site(Path(tmp), html)
            return check_site.check_site(public, Path(tmp) / "hugo.toml")

    def test_good_page_passes(self) -> None:
        self.assertEqual(self.problems(GOOD), [])

    def test_catches_broken_link_and_missing_fragment(self) -> None:
        found = self.problems(GOOD.replace('href="/other/"', 'href="/missing/"').replace('href="#top"', 'href="#nowhere"'))
        self.assertTrue(any("broken internal link: /missing/" in p for p in found), found)
        self.assertTrue(any("missing #fragment: #nowhere" in p for p in found), found)

    def test_catches_csp_hazards_and_foreign_hosts(self) -> None:
        bad = GOOD.replace("<p>", '<p style="color:red" onclick="x()">').replace(
            "</body>", '<script>alert(1)</script><img src="https://evil.example/x.png" alt=""><a href="javascript:x">j</a></body>'
        )
        found = "\n".join(self.problems(bad))
        for needle in ("style= attribute", "inline event handler onclick", "inline <script>", "outside the allowlist", "non-http(s) URL"):
            self.assertIn(needle, found)

    def test_catches_scan_address_with_empty_item_id(self) -> None:
        bad = GOOD.replace('src="https://archive.org/x.jpg"', 'src="https://archive.org/download//page/n3_w600.jpg"')
        self.assertTrue(any("empty item id" in p for p in self.problems(bad)))

    def test_external_links_are_fine_but_not_external_resources(self) -> None:
        ok = GOOD.replace("</body>", '<a href="https://founders.archives.gov/x">source</a></body>')
        self.assertEqual(self.problems(ok), [])

    def test_catches_structure_errors(self) -> None:
        bad = GOOD.replace("<h1 id=\"top\">Hi</h1>", '<h1 id="top">Hi</h1><h1 id="top">Again</h1><div><span></div>').replace(' alt=""', "")
        found = "\n".join(self.problems(bad))
        for needle in ("duplicate id 'top'", "exactly one <h1>", "does not match", "has no alt"):
            self.assertIn(needle, found)

    def test_catches_template_errors_printed_into_a_page(self) -> None:
        found = self.problems(GOOD.replace("</body>", "<p>%!s(<nil>)</p></body>"))
        self.assertTrue(any("printed an error instead of text" in p for p in found), found)

    def feed_problems(self, item: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            public = write_site(Path(tmp), GOOD)
            (public / "journal").mkdir()
            (public / "journal" / "rss.xml").write_text(f'<?xml version="1.0"?><rss version="2.0"><channel><title>J</title>{item}</channel></rss>', encoding="utf-8")
            return check_site.check_feeds(public)

    def test_feeds_must_be_escaped_once_with_absolute_links(self) -> None:
        good = "<item><title>Tom &amp; Jerry</title><description>&lt;p&gt;Hi&amp;rsquo; &lt;a href=&quot;https://paperlanterns.ink/x/&quot;&gt;x&lt;/a&gt;&lt;/p&gt;</description></item>"
        self.assertEqual(self.feed_problems(good), [])
        twice = "<item><title>Tom &amp;amp; Jerry</title><description>&amp;lt;p&amp;gt;Hi</description></item>"
        found = self.feed_problems(twice)
        self.assertEqual(sum("escaped twice" in p for p in found), 2, found)
        relative = "<item><title>T</title><description>&lt;img src=&quot;/journal/a.webp&quot; alt=&quot;&quot;&gt;</description></item>"
        self.assertTrue(any("relative address" in p for p in self.feed_problems(relative)))

    def test_every_page_needs_a_1200x630_share_card_from_this_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = write_site(Path(tmp), GOOD)
            (public / "card.png").write_bytes(png_header(600, 315))
            (public / "other" / "card.html").write_text(GOOD, encoding="utf-8")
            found = check_site.check_site(public, Path(tmp) / "hugo.toml")
        self.assertTrue(any("not a 1200x630 PNG or JPEG" in p for p in found), found)
        self.assertTrue(any("share card page left in the build" in p for p in found), found)
        missing = self.problems(GOOD.replace("https://paperlanterns.ink/card.png", "https://paperlanterns.ink/nope.png"))
        self.assertTrue(any("is not in the build" in p for p in missing), missing)
        hotlinked = self.problems(GOOD.replace("https://paperlanterns.ink/card.png", "https://archive.org/x.jpg"))
        self.assertTrue(any("not an absolute https://paperlanterns.ink/" in p for p in hotlinked), hotlinked)
        small = self.problems(GOOD.replace('content="summary_large_image"', 'content="summary"').replace('og:image:alt" content="a"', 'og:image:alt" content=""'))
        self.assertTrue(any("twitter:card is not summary_large_image" in p for p in small), small)
        self.assertTrue(any("no og:image:alt" in p for p in small), small)

    def test_image_size_reads_png_and_jpeg_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png, jpg, other = Path(tmp) / "a.png", Path(tmp) / "a.jpg", Path(tmp) / "a.gif"
            png.write_bytes(png_header(1200, 630))
            # SOI, an APP0 segment, then a baseline SOF0 frame header: length, precision, height, width.
            jpg.write_bytes(b"\xff\xd8\xff\xe0\x00\x04ab\xff\xc0\x00\x11\x08" + (630).to_bytes(2, "big") + (1200).to_bytes(2, "big") + b"\x03" + b"\x00" * 9)
            other.write_bytes(b"GIF89a")
            self.assertEqual(check_site.image_size(png), ("png", 1200, 630))
            self.assertEqual(check_site.image_size(jpg), ("jpeg", 1200, 630))
            self.assertIsNone(check_site.image_size(other))

    def test_book_pages_must_show_one_reading_score(self) -> None:
        rel = Path("collections/some-book/index.html")
        self.assertEqual(check_site.check_reading_score(rel, ["76"]), [])
        self.assertEqual(check_site.check_reading_score(Path("collections/index.html"), []), [])
        self.assertEqual(check_site.check_reading_score(Path("collections/some-book/3/index.html"), []), [])
        for scores, needle in (([], "exactly one"), (["%!g(<nil>)"], "not a number"), (["130"], "outside")):
            self.assertIn(needle, check_site.check_reading_score(rel, scores)[0])

    def test_jsonld_is_allowed_but_must_parse(self) -> None:
        ok = GOOD.replace("</head>", '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Book"}</script></head>')
        self.assertEqual(self.problems(ok), [])
        bad = GOOD.replace("</head>", '<script type="application/ld+json">{"@type": oops}</script></head>')
        self.assertTrue(any("JSON-LD does not parse" in p for p in self.problems(bad)))

    def test_catches_csp_drift_between_headers_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = write_site(Path(tmp), GOOD)
            (public / "_headers").write_text("/*\n  Content-Security-Policy: default-src *\n", encoding="utf-8")
            found = check_site.check_site(public, Path(tmp) / "hugo.toml")
        self.assertTrue(any("_headers CSP" in p for p in found), found)

    def test_discovery_checks_robots_sitemap_and_llms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = write_site(Path(tmp), GOOD)
            (public / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
            (public / "sitemap.xml").write_text(
                '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://paperlanterns.ink/search/</loc></url></urlset>",
                encoding="utf-8",
            )
            (public / "llms.txt").write_text("empty\n", encoding="utf-8")
            (public / "cmif.xml").write_text("<TEI/>", encoding="utf-8")
            (public / ".well-known").mkdir()
            (public / ".well-known" / "tdmrep.json").write_text("{bad", encoding="utf-8")
            found = "\n".join(check_site.check_discovery(public))
            self.assertIn("Sitemap:", found)
            self.assertIn("/search/", found)
            self.assertIn("Paper Lanterns heading", found)
            self.assertIn("<correspDesc>", found)
            self.assertIn("tdmrep.json", found)


class IndexNowTests(unittest.TestCase):
    def test_reads_sitemap_and_builds_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sm = Path(tmp) / "sitemap.xml"
            sm.write_text(
                '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://paperlanterns.ink/</loc></url>"
                "<url><loc>https://paperlanterns.ink/collections/</loc></url></urlset>",
                encoding="utf-8",
            )
            urls = ping_indexnow.urls_from_sitemap(sm)
            self.assertEqual(urls, ["https://paperlanterns.ink/", "https://paperlanterns.ink/collections/"])
            payload = ping_indexnow.build_payload("paperlanterns.ink", "abc123", urls)
            self.assertEqual(payload["keyLocation"], "https://paperlanterns.ink/abc123.txt")
            self.assertEqual(payload["urlList"], urls)


def make_pipeline(root: Path, *, tamper: bool = False) -> Path:
    ed = root / "pipeline" / "library" / "world-correspondence" / "test-book-1900"
    (ed / "hugo").mkdir(parents=True)
    (ed / "epub").mkdir()
    (ed / "hugo" / "_index.md").write_text('{"title": "Book"}\n', encoding="utf-8")
    (ed / "hugo" / "letter-0001.md").write_text('{"title": "I"}\n', encoding="utf-8")
    epub = ed / "epub" / "test-book-1900.epub"
    epub.write_bytes(b"epub-bytes")
    digest = hashlib.sha256(b"epub-bytes" if not tamper else b"other").hexdigest()
    manifest = {
        "pages": ["_index.md", "letter-0001.md"],
        "downloads": [{"from": "epub/test-book-1900.epub", "to": "test-book-1900.epub", "sha256": digest}],
    }
    (ed / "hugo" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root / "pipeline"


class SyncTests(unittest.TestCase):
    def test_sync_copies_pages_and_downloads_and_removes_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = make_pipeline(root)
            site = root / "site"
            stale = site / "content" / "collections" / "test-book-1900" / "letter-9999.md"
            stale.parent.mkdir(parents=True)
            stale.write_text("{}", encoding="utf-8")

            sync.sync_book(pipeline, "test-book-1900", site_root=site)

            pages = sorted(p.name for p in (site / "content" / "collections" / "test-book-1900").iterdir())
            self.assertEqual(pages, ["_index.md", "letter-0001.md"])
            self.assertTrue((site / "static" / "collections" / "test-book-1900" / "test-book-1900.epub").is_file())
            self.assertEqual(sync.stale_files(pipeline, "test-book-1900", site_root=site), [])

            (site / "content" / "collections" / "test-book-1900" / "letter-0001.md").write_text("edited", encoding="utf-8")
            self.assertEqual(sync.stale_files(pipeline, "test-book-1900", site_root=site), ["content/letter-0001.md"])

    def test_hash_mismatch_stops_sync_and_leaves_site_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = make_pipeline(root, tamper=True)
            site = root / "site"
            site.mkdir()
            with self.assertRaises(sync.SyncError):
                sync.sync_book(pipeline, "test-book-1900", site_root=site)
            self.assertFalse((site / "content").exists())

    def test_rejects_bad_book_ids_and_path_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = make_pipeline(root)
            with self.assertRaises(sync.SyncError):
                sync.find_edition_dir(pipeline, "../etc")
            manifest = pipeline / "library" / "world-correspondence" / "test-book-1900" / "hugo" / "manifest.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["downloads"][0]["from"] = "../../../../outside.epub"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(sync.SyncError):
                sync.plan_copies(manifest.parent.parent)


class AddressLedgerTests(unittest.TestCase):
    def make(self, root: Path, pages: list[str]) -> Path:
        public = root / "public"
        for page in pages:
            d = public / page.strip("/")
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text("x", encoding="utf-8")
        return public

    def test_share_cards_are_not_ledger_addresses_but_downloads_are(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = self.make(Path(tmp), ["/collections/b/", "/collections/b/1/"])
            (public / "collections" / "b" / "card.jpg").write_bytes(b"x")
            (public / "collections" / "b" / "1" / "card.png").write_bytes(b"x")
            (public / "collections" / "b" / "b.epub").write_bytes(b"x")
            self.assertEqual(addresses.served_addresses(public), {"/collections/b/", "/collections/b/1/", "/collections/b/b.epub"})

    def test_update_then_check_passes_and_never_drops_addresses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = self.make(root, ["/", "/collections/book/", "/collections/book/20/"])
            (public / "collections" / "book" / "book.epub").write_text("e", encoding="utf-8")
            ledger, redirects = root / "ledger.txt", root / "_redirects"
            addresses.update(public, ledger)
            self.assertIn("/collections/book/book.epub", addresses.read_ledger(ledger))
            self.assertEqual(addresses.check(public, ledger, redirects, root / "none.txt"), [])
            smaller = self.make(root / "b", ["/"])
            addresses.update(smaller, ledger)
            self.assertIn("/collections/book/20/", addresses.read_ledger(ledger))

    def test_removed_address_fails_until_redirected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger, redirects = root / "ledger.txt", root / "_redirects"
            addresses.update(self.make(root / "old", ["/", "/collections/book/20/"]), ledger)
            moved = self.make(root / "new", ["/", "/collections/book/21/"])
            addresses.update(moved, ledger)
            found = addresses.check(moved, ledger, redirects, root / "none.txt")
            self.assertTrue(any("no longer served" in p and "/collections/book/20/" in p for p in found), found)
            redirects.write_text("# moved after a re-split\n/collections/book/20/ /collections/book/21/ 301\n", encoding="utf-8")
            self.assertEqual(addresses.check(moved, ledger, redirects, root / "none.txt"), [])
            redirects.write_text("/collections/book/20/ /collections/book/99/ 301\n", encoding="utf-8")
            self.assertTrue(any("redirect target is not served" in p for p in addresses.check(moved, ledger, redirects, root / "none.txt")))

    def test_unlisted_address_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.txt"
            addresses.update(self.make(root / "a", ["/"]), ledger)
            found = addresses.check(self.make(root / "b", ["/", "/new/"]), ledger, root / "_redirects", root / "none.txt")
            self.assertTrue(any("not in the ledger" in p for p in found), found)


class LedgerFilesAndLegacyTests(unittest.TestCase):
    def test_file_addresses_and_legacy_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "public"
            (public / "api").mkdir(parents=True)
            (public / "index.html").write_text("x", encoding="utf-8")
            (public / "rss.xml").write_text("x", encoding="utf-8")
            ledger, legacy = root / "ledger.txt", root / "legacy.txt"
            ledger.write_text("/\n/rss.xml\n", encoding="utf-8")
            legacy.write_text("/rss.xml\n/api/random-content.json\n", encoding="utf-8")
            found = addresses.check(public, ledger, root / "_redirects", legacy)
            self.assertTrue(any("old-site address missing from the ledger: /api/random-content.json" in p for p in found), found)
            (public / "rss.xml").unlink()
            ledger.write_text("/\n/rss.xml\n/api/random-content.json\n", encoding="utf-8")
            found = addresses.check(public, ledger, root / "_redirects", legacy)
            self.assertTrue(any("no longer served" in p and "/rss.xml" in p for p in found), found)


class BuildIndexesTests(unittest.TestCase):
    def test_credits_keep_their_recorded_role(self) -> None:
        self.assertEqual(build_indexes.split_credit("Ethel Colburn Mayne (tr.)"), ("Ethel Colburn Mayne", "tr."))
        self.assertEqual(build_indexes.split_credit("Victor Hugo"), ("Victor Hugo", ""))

    def test_people_join_same_person_forms_and_count_exact_signatures_only(self) -> None:
        books = [{"book_id": "b", "authors": ["M. K. Gandhi", "R. L. Khipple (ed.)"]}]
        letters = [
            {"path": "/collections/b/1", "book_id": "b", "iso": "1920", "names": {"Mahatma Gandhi"}},
            {"path": "/collections/b/2", "book_id": "b", "iso": "1930", "names": {"M. K. Gandhi", "Gandhi"}},
            {"path": "/collections/b/3", "book_id": "b", "iso": "", "names": {"Gandhiji"}},
        ]
        curated = [{"path": "/letters/x", "section": "letters", "author": "Mohandas K. Gandhi", "year": 1931}]
        same = {"Mahatma Gandhi": "M. K. Gandhi", "Mohandas K. Gandhi": "M. K. Gandhi"}
        people = {p["slug"]: p for p in build_indexes.build_people(books, letters, curated, same)}
        g = people["m-k-gandhi"]
        self.assertEqual(g["letters"], {"b": 2})
        self.assertEqual(g["curated"], ["/letters/x"])
        self.assertEqual(people["r-l-khipple"]["credits"], [{"book_id": "b", "role": "ed."}])
        self.assertNotIn("gandhiji", people)

    def test_decades_include_curated_letters_and_skip_undated(self) -> None:
        letters = [{"path": "/collections/b/1", "book_id": "b", "iso": "1849-12-22", "names": set()},
                   {"path": "/collections/b/2", "book_id": "b", "iso": "", "names": set()}]
        curated = [{"path": "/letters/s", "section": "letters", "author": "Seneca", "year": 62},
                   {"path": "/essays/e", "section": "essays", "author": "X", "year": 1845}]
        decades = {d["slug"]: d for d in build_indexes.build_decades(letters, curated)}
        self.assertEqual(sorted(decades), ["1840s", "60s"])
        self.assertEqual(decades["1840s"]["count"], 1)
        self.assertEqual(decades["60s"]["curated"], ["/letters/s"])


class ImportLegacyTests(unittest.TestCase):
    def test_poems_headings_and_short_years_convert_without_losing_words(self) -> None:
        src = (
            '---\ntitle: "T"\ndate: 62-01-01\n---\n\nPlain text.\n\n'
            '<div class="poem-container" style="x">\n<h5>THE ROAD</h5>\n    First line,<br/>\n    second line.\n</div>\n'
        )
        out = import_legacy.convert(src, "t.md")
        self.assertIn("date: 0062-01-01", out)
        self.assertIn("##### THE ROAD\n\nFirst line,\\\nsecond line.\n{.poem}", out)
        self.assertNotIn("<", out.split("---", 2)[2])

    def test_unknown_raw_html_stops_the_import(self) -> None:
        with self.assertRaises(import_legacy.ImportError_):
            import_legacy.convert('---\ntitle: "T"\n---\n\n<table><tr><td>x</td></tr></table>\n', "t.md")

    def test_private_garden_notes_and_disabled_files_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp)
            for d in import_legacy.SECTIONS:
                (old / "src" / "content" / d).mkdir(parents=True)
            (old / "src" / "content" / "letters" / "a.md").write_text('---\ntitle: "A"\n---\nx\n', encoding="utf-8")
            (old / "src" / "content" / "letters" / "b.md.disabled").write_text('---\ntitle: "B"\n---\nx\n', encoding="utf-8")
            (old / "src" / "content" / "garden" / "p.md").write_text('---\ntitle: "P"\nprivate: true\n---\nx\n', encoding="utf-8")
            names = sorted(p.name for p in import_legacy.plan(old))
            self.assertEqual(names, ["a.md"])


class SecurityPolicyTests(unittest.TestCase):
    """The policy blocked Cloudflare's visitor-count beacon after launch, so no visits were counted (D33)."""

    def directive(self, name: str) -> list[str]:
        config = tomllib.loads((Path(__file__).resolve().parents[1] / "hugo.toml").read_text(encoding="utf-8"))
        policy = config["params"]["security"]["csp"]
        for part in policy.split(";"):
            words = part.split()
            if words and words[0] == name:
                return words[1:]
        self.fail(f"{name} is missing from params.security.csp")

    def test_the_analytics_beacon_may_load(self) -> None:
        self.assertIn("https://static.cloudflareinsights.com", self.directive("script-src"))

    def test_the_analytics_beacon_may_report(self) -> None:
        self.assertIn("https://cloudflareinsights.com", self.directive("connect-src"))

    def test_no_other_script_source_is_allowed(self) -> None:
        self.assertEqual(
            self.directive("script-src"),
            ["'self'", "'wasm-unsafe-eval'", "https://static.cloudflareinsights.com"],
        )


class EditorialNotesTests(unittest.TestCase):
    def test_book_and_people_notes_reference_valid_ids_and_https_links(self) -> None:
        root = Path(__file__).resolve().parents[1]
        books = {p.parent.name for p in (root / "content" / "collections").glob("*/_index.md")}
        people = {p["slug"] for p in json.loads((root / "data" / "people.json").read_text(encoding="utf-8"))}
        bnotes = json.loads((root / "data" / "book-notes.json").read_text(encoding="utf-8"))
        pnotes = json.loads((root / "data" / "people-notes.json").read_text(encoding="utf-8"))
        self.assertEqual(set(bnotes), books)
        for bid, entry in bnotes.items():
            self.assertTrue(entry.get("book"), f"{bid}: missing book prose")
            for rel in entry.get("related", []):
                self.assertIn(rel, books, f"{bid}: unknown related book {rel}")
            for person in entry.get("people", []):
                if "slug" in person:
                    self.assertIn(person["slug"], people, f"{bid}: unknown person slug {person['slug']}")
            for link in entry.get("links", []):
                self.assertTrue(link["url"].startswith("https://"), f"{bid}: non-https link {link['url']}")
        for slug, entry in pnotes.items():
            self.assertIn(slug, people, f"unknown slug in people-notes.json: {slug}")
            for key in ("wikipedia", "wikisource"):
                if key in entry:
                    self.assertTrue(entry[key].startswith("https://"), f"{slug}: non-https {key}")


class LetterTemplateContractTests(unittest.TestCase):
    def test_letter_template_renders_structured_table_cells_and_illustration_runs(self) -> None:
        hugo = shutil.which(os.environ.get("HUGO") or "hugo")
        self.assertIsNotNone(hugo, "hugo binary must be installed on PATH or HUGO env")
        site_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "site"
            out = root / "out"
            src.mkdir()
            for name in ("hugo.toml", "layouts", "assets", "data"):
                (src / name).symlink_to(site_root / name)
            coll = src / "content" / "collections"
            book = coll / "fixture"
            book.mkdir(parents=True)
            (coll / "_index.md").write_text('+++\ntitle = "The collections"\n+++\n', encoding="utf-8")
            (book / "_index.md").write_text(
                json.dumps(
                    {
                        "title": "Fixture Correspondence",
                        "layout": "book",
                        "book_id": "fixture",
                        "collection": "world-correspondence",
                        "authors": ["Test Author"],
                        "year": 1909,
                        "language": "en",
                        "provenance_tier": "community",
                        "counts": {"letters": 1, "notes": 2, "pages": 1, "dated_letters": 1},
                        "quality": {"score": 97.5, "out_of": 100.0},
                        "proof": {"total_pages": 1, "p1_proofed": 0, "verified": 0, "machine_reread": 0},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (book / "1.md").write_text(
                json.dumps(
                    {
                        "title": "My dear Friend...",
                        "heading": "Letter 1",
                        "page_title": "A to B, 1 May 1909",
                        "layout": "letter",
                        "weight": 1,
                        "description": "Fixture letter with table and illustration fnref.",
                        "book_id": "fixture",
                        "letter_id": "letter-0001",
                        "sequence": 1,
                        "letter_count": 1,
                        "section_id": "sec-02",
                        "letter_date": {"iso": "1909-05-01", "display": "1 May 1909", "short": "1 · V · 1909"},
                        "place": "Vienna",
                        "sender": "A",
                        "recipient": "B",
                        "start_page": 1,
                        "end_page": 1,
                        "start_folio": "1",
                        "end_folio": "1",
                        "pages": [{"page": 1, "leaf": 0, "folio": "1"}],
                        "archive_id": "fixture_item",
                        "blocks": [
                            {
                                "id": "p0001-b0001",
                                "type": "table_row",
                                "table_role": "header",
                                "align": "left",
                                "page": 1,
                                "bbox": [10, 10, 90, 20],
                                "lines": [[{"t": "Col 1 | Col 2"}]],
                                "cells": [
                                    {"colspan": 2, "rowspan": 1, "lines": [[{"t": "Wide Header"}, {"t": "*", "tag": "sup", "fn": "fn-p0001-1"}]]},
                                ],
                            },
                            {
                                "id": "p0001-b0002",
                                "type": "table_row",
                                "table_role": "body",
                                "align": "left",
                                "page": 1,
                                "bbox": [10, 22, 90, 32],
                                "lines": [[{"t": "A | B"}]],
                                "cells": [
                                    {"colspan": 1, "rowspan": 1, "lines": [[{"t": "Cell A"}]]},
                                    {"colspan": 1, "rowspan": 1, "lines": [[{"t": "Cell B"}]]},
                                ],
                            },
                            {
                                "id": "p0001-b0003",
                                "type": "illustration",
                                "align": "center",
                                "page": 1,
                                "bbox": [10, 40, 90, 70],
                                "lines": [[{"t": "[Musical notation]"}, {"t": "†", "tag": "sup", "fn": "fn-p0001-2"}]],
                            },
                        ],
                        "footnotes": [
                            {"id": "fn-p0001-1", "label": "*", "page": 1, "is_orphan": False, "lines": [[{"t": "Table note."}]]},
                            {"id": "fn-p0001-2", "label": "†", "page": 1, "is_orphan": False, "lines": [[{"t": "Score note."}]]},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [str(hugo), "--source", str(src), "--destination", str(out), "--panicOnWarning", "--disableKinds", "home,RSS,sitemap,taxonomy,term"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"{proc.stderr}\n{proc.stdout}")
            rendered = out / "collections" / "fixture" / "1" / "index.html"
            html = rendered.read_text(encoding="utf-8")
            self.assertIn('<table class="letter-table">', html)
            self.assertIn('colspan="2"', html)
            self.assertIn("Wide Header", html)
            self.assertIn('href="#fn-p0001-1"', html)
            self.assertIn("Cell B", html)
            self.assertIn('class="illu-caption"', html)
            self.assertIn("[Musical notation]", html)
            self.assertIn('href="#fn-p0001-2"', html)
            self.assertEqual(check_site.parse_page(rendered).errors, [])


if __name__ == "__main__":
    unittest.main()
