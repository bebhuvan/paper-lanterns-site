"""Check the built site in public/ for broken structure, links and CSP hazards. Standard library only.

It fails (exit 1) on:
  - HTML that is not well formed: unclosed or mismatched elements, duplicate ids;
  - pages without <html lang>, a <title>, a meta description or exactly one <h1>;
  - <img> without alt text;
  - inline <script>/<style>, style="" or on*="" attributes (the CSP forbids them, so they would silently break);
    the one exception is <script type="application/ld+json">, which browsers never run and which must parse as JSON;
  - internal links or #fragments that point at nothing in public/;
  - images, scripts or stylesheets from hosts outside the allowlist, and any non-http(s) URL scheme
    (ordinary links may point to any http or https site);
  - a _headers CSP that differs from the dev-server CSP in hugo.toml;
  - a page whose share card (og:image, D31) is missing, is not on this site, or is not a 1200x630 PNG or JPEG
    in the build, or whose og:image size, alt text and twitter tags are missing; and any card.html left undrawn.
It is not a full W3C validator; it catches the mistakes this site can actually make.

Usage: python3 scripts/check_site.py [public]
"""

from __future__ import annotations

import json
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE_ROOT = Path(__file__).resolve().parents[1]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# SVG shapes may self-close; nothing else should.
SELF_CLOSING_OK = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "use", "stop"}
ALLOWED_HOSTS = {"archive.org", "akshara.ink", "paperlanterns.ink"}
URL_ATTRS = {("a", "href"), ("img", "src"), ("link", "href"), ("script", "src"), ("source", "src")}


@dataclass
class PageReport:
    ids: set[str] = field(default_factory=set)
    links: list[tuple[str, bool]] = field(default_factory=list)  # (url, True if a navigation link <a href>)
    errors: list[str] = field(default_factory=list)
    h1: int = 0
    has_lang: bool = False
    has_title: bool = False
    has_description: bool = False
    jsonld: list[str] = field(default_factory=list)
    reading_scores: list[str] = field(default_factory=list)  # data-reading-score values (D24)
    meta: dict[str, str] = field(default_factory=dict)  # og:* and twitter:* tags


class PageParser(HTMLParser):
    def __init__(self, report: PageReport) -> None:
        super().__init__(convert_charrefs=True)
        self.r = report
        self.stack: list[str] = []
        self.in_jsonld = False

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.startswith("on"):
                self.r.errors.append(f"inline event handler {name}= on <{tag}>")
            if name == "style":
                self.r.errors.append(f"style= attribute on <{tag}> (blocked by CSP)")
            if name == "id" and value is not None:
                if value in self.r.ids:
                    self.r.errors.append(f"duplicate id {value!r}")
                self.r.ids.add(value)
            if (tag, name) in URL_ATTRS and value:
                self.r.links.append((value, tag == "a"))
            if name == "data-reading-score":
                self.r.reading_scores.append(value or "")
            if name == "srcset" and value:
                self.r.links.extend((part.strip().split(" ")[0], False) for part in value.split(",") if part.strip())
        d = dict(attrs)
        if tag == "img" and "alt" not in d:
            self.r.errors.append(f"<img src={d.get('src')!r}> has no alt attribute")
        if tag == "script" and d.get("type") == "application/ld+json":
            self.in_jsonld = True
            self.r.jsonld.append("")
        elif tag == "script" and not d.get("src"):
            self.r.errors.append("inline <script> (blocked by CSP)")
        if tag == "html" and d.get("lang"):
            self.r.has_lang = True
        if tag == "meta" and d.get("name") == "description" and d.get("content"):
            self.r.has_description = True
        key = d.get("property") or d.get("name") or ""
        if tag == "meta" and key.startswith(("og:", "twitter:")):
            self.r.meta[key] = d.get("content") or ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._attrs(tag, attrs)
        if tag == "style":
            self.r.errors.append("inline <style> (blocked by CSP)")
        if tag == "h1":
            self.r.h1 += 1
        if tag == "title" and "svg" not in self.stack:
            self.r.has_title = True
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._attrs(tag, attrs)
        if tag not in VOID and tag not in SELF_CLOSING_OK:
            self.r.errors.append(f"<{tag}/> self-closed outside SVG")

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.r.jsonld[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_jsonld = False
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.r.errors.append(f"</{tag}> does not match open <{self.stack[-1] if self.stack else 'nothing'}>")
            if tag in self.stack:
                del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag) :]
            return
        self.stack.pop()

    def close(self) -> None:
        super().close()
        if self.stack:
            self.r.errors.append(f"unclosed elements at end of file: {self.stack}")


def parse_page(path: Path) -> PageReport:
    report = PageReport()
    parser = PageParser(report)
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    if not report.has_lang:
        report.errors.append("<html> has no lang attribute")
    if not report.has_title:
        report.errors.append("no <title>")
    if not report.has_description:
        report.errors.append("no meta description")
    for block in report.jsonld:
        try:
            data = json.loads(block)
        except ValueError as exc:
            report.errors.append(f"JSON-LD does not parse: {exc}")
            continue
        if not isinstance(data, dict) or data.get("@context") != "https://schema.org" or "@type" not in data:
            report.errors.append("JSON-LD lacks a schema.org @context and @type")
    if report.h1 != 1:
        report.errors.append(f"expected exactly one <h1>, found {report.h1}")
    return report


def _target_for(public: Path, page: Path, path: str) -> Path:
    base = public if path.startswith("/") else page.parent
    target = (base / unquote(path.lstrip("/"))).resolve()
    return target / "index.html" if target.is_dir() or path.endswith("/") else target


def check_link(public: Path, page: Path, url: str, ids_by_file: dict[Path, set[str]], *, navigation: bool = False) -> str | None:
    """Resources (images, scripts, stylesheets) must come from allowlisted hosts; links may go to any http(s) site."""
    parts = urlsplit(url)
    if parts.scheme in {"http", "https"}:
        host = (parts.hostname or "").lower()
        if host.endswith("archive.org") and ("/download//" in parts.path or parts.path.rstrip("/") in {"/details", "/download"}):
            return f"Internet Archive address with an empty item id: {url}"
        if host in {"localhost", "127.0.0.1"}:
            return f"link to a local server: {url}"
        if not navigation and not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
            return f"resource from a host outside the allowlist: {url}"
        return None
    if parts.scheme or url.startswith("//"):
        return f"non-http(s) URL: {url}"
    target = page if not parts.path else _target_for(public, page, parts.path)
    if public.resolve() not in target.parents and target != public.resolve():
        return f"link escapes the site: {url}"
    if not target.exists():
        return f"broken internal link: {url}"
    if parts.fragment and target.suffix == ".html":
        if target not in ids_by_file:
            ids_by_file[target] = parse_page(target).ids
        if unquote(parts.fragment) not in ids_by_file[target]:
            return f"missing #fragment: {url}"
    return None


def check_headers(public: Path, hugo_toml: Path) -> list[str]:
    headers = public / "_headers"
    if not headers.is_file():
        return ["public/_headers is missing (Cloudflare would serve no CSP)"]
    csp_lines = [ln.split(":", 1)[1].strip() for ln in headers.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("Content-Security-Policy:")]
    config = tomllib.loads(hugo_toml.read_text(encoding="utf-8"))
    dev = [h["values"].get("Content-Security-Policy") for h in config.get("server", {}).get("headers", [])]
    want = config["params"]["security"]["csp"]
    errors = []
    if csp_lines != [want]:
        errors.append(f"_headers CSP {csp_lines!r} differs from params.security.csp")
    if dev != [want]:
        errors.append("hugo.toml [server.headers] CSP differs from params.security.csp")
    return errors


def check_reading_score(rel: Path, scores: list[str]) -> list[str]:
    """Every book page (collections/<book_id>/index.html) shows exactly one reading score between 0 and 100 (D24)."""
    if len(rel.parts) != 3 or rel.parts[0] != "collections" or rel.name != "index.html":
        return []
    if len(scores) != 1:
        return [f"book page needs exactly one reading score, found {len(scores)}"]
    try:
        value = float(scores[0])
    except ValueError:
        return [f"reading score {scores[0]!r} is not a number"]
    return [] if 0 <= value <= 100 else [f"reading score {value} is outside 0-100"]


def image_size(path: Path) -> tuple[str, int, int] | None:
    """(format, width, height) of a PNG or baseline/progressive JPEG, read from its header; None for anything else."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        return None
    at = 2
    while at + 9 < len(data):
        if data[at] != 0xFF:
            return None
        marker, length = data[at + 1], int.from_bytes(data[at + 2 : at + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return "jpeg", int.from_bytes(data[at + 7 : at + 9], "big"), int.from_bytes(data[at + 5 : at + 7], "big")
        at += 2 + length
    return None


def check_share_card(public: Path, meta: dict[str, str], sizes: dict[Path, tuple[str, int, int] | None]) -> list[str]:
    """The page names a 1200x630 share card that this build contains (D31), with its size, alt text and twitter tags."""
    image = meta.get("og:image", "")
    if not image:
        return ["no og:image"]
    parts = urlsplit(image)
    if parts.scheme != "https" or parts.hostname != "paperlanterns.ink":
        return [f"og:image {image!r} is not an absolute https://paperlanterns.ink/ address"]
    errors = []
    target = (public / unquote(parts.path.lstrip("/"))).resolve()
    if not target.is_file() or not target.is_relative_to(public.resolve()):
        errors.append(f"og:image {parts.path} is not in the build")
    else:
        if target not in sizes:
            sizes[target] = image_size(target)
        found = sizes[target]
        if found is None or found[1:] != (1200, 630):
            errors.append(f"og:image {parts.path} is {found}, not a 1200x630 PNG or JPEG")
    if meta.get("og:image:width") != "1200" or meta.get("og:image:height") != "630":
        errors.append("og:image:width and og:image:height must be 1200 and 630")
    if not meta.get("og:image:alt"):
        errors.append("no og:image:alt")
    if meta.get("twitter:card") != "summary_large_image":
        errors.append("twitter:card is not summary_large_image")
    if meta.get("twitter:image") != image:
        errors.append("twitter:image differs from og:image")
    return errors


def check_site(public: Path, hugo_toml: Path) -> list[str]:
    problems: list[str] = []
    pages = sorted(public.rglob("*.html"))
    if not pages:
        return [f"no HTML pages under {public}"]
    undrawn = [p for p in pages if p.name == "card.html"]
    problems.extend(f"{p.relative_to(public)}: share card page left in the build (run scripts/og_cards.mjs)" for p in undrawn)
    pages = [p for p in pages if p.name != "card.html"]
    ids_by_file: dict[Path, set[str]] = {}
    sizes: dict[Path, tuple[str, int, int] | None] = {}
    for page in pages:
        report = parse_page(page)
        ids_by_file[page.resolve()] = report.ids
        rel = page.relative_to(public)
        problems.extend(f"{rel}: {e}" for e in report.errors)
        problems.extend(f"{rel}: {e}" for e in check_reading_score(rel, report.reading_scores))
        problems.extend(f"{rel}: {e}" for e in check_share_card(public, report.meta, sizes))
        for url, navigation in report.links:
            err = check_link(public, page.resolve(), url, ids_by_file, navigation=navigation)
            if err:
                problems.append(f"{rel}: {err}")
    problems.extend(check_headers(public, hugo_toml))
    problems.extend(check_feeds(public))
    return problems


def check_feeds(public: Path) -> list[str]:
    """The feed must be well-formed XML and every .json file must parse."""
    import xml.etree.ElementTree as ET  # our own build output, not untrusted input

    errors = []
    for feed in public.glob("*.xml"):
        try:
            ET.parse(feed)
        except ET.ParseError as exc:
            errors.append(f"{feed.name}: not well-formed XML: {exc}")
    for data in list(public.glob("*.json")) + list((public / "api").glob("*.json")):
        try:
            json.loads(data.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{data.relative_to(public)}: does not parse as JSON: {exc}")
    return errors


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    public = Path(args[0]) if args else SITE_ROOT / "public"
    problems = check_site(public, SITE_ROOT / "hugo.toml")
    for p in problems:
        print(p, file=sys.stderr)
    pages = len(list(public.rglob("*.html")))
    if problems:
        print(f"check_site: {len(problems)} problem(s) in {pages} pages", file=sys.stderr)
        return 1
    print(f"check_site: {pages} pages, all links, ids, CSP rules and 1200x630 share cards OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
