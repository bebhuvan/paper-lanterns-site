"""Import the old Astro site's hand-curated content into this site at the same addresses.

Source (read only): <old-repo>/src/content/{letters,essays,lectures,speeches,garden,collections}/*.md
Target: content/{letters,essays,lectures,speeches,garden,sets}/<same file name>.md

Files are copied verbatim (Hugo reads their YAML front matter as is), so the hand-written titles, sources,
context and links stay exactly as published. Two deliberate exceptions, both recorded in DECISIONS.md D15:
  - files the old site did not publish are skipped: `*.md.disabled`, and garden notes marked `private: true`;
  - raw HTML poem blocks (`<div class="poem-container" ...>` with `<br/>`) become Markdown lines with hard breaks
    and a `{.poem}` class, and whole-line `<hN>` headings become Markdown headings, because this site never
    renders raw HTML;
  - dates with a one- to three-digit year (`date: 62-01-01`, which the old site showed as 1962) are padded to
    four digits (`0062-01-01`) so they mean AD 62.
Standard library only.

Usage:
    python3 scripts/import_legacy.py "<old-repo>"            # copy
    python3 scripts/import_legacy.py --check "<old-repo>"    # exit 1 if this site's copy differs
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1]
SECTIONS = {
    "letters": "letters",
    "essays": "essays",
    "lectures": "lectures",
    "speeches": "speeches",
    "garden": "garden",
    "collections": "sets",
}
_POEM_RE = re.compile(r"<div class=\"poem-container\"[^>]*>(.*?)</div>", re.S)
_BR_RE = re.compile(r"\s*<br\s*/?>\s*")
_HEADING_RE = re.compile(r"^\s*<h([1-6])>(.*?)</h\1>[ \t]*$", re.M)
_PRIVATE_RE = re.compile(r"^private:\s*true\s*$", re.M)
_ANY_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
# YAML `date: 62-01-01` is not a date; the old site read it as 1962. Pad first-millennium years so it means AD 62.
_SHORT_YEAR_RE = re.compile(r"^date: (\d{1,3})-(\d{2})-(\d{2})\s*$", re.M)


class ImportError_(RuntimeError):
    """The old content cannot be imported without guessing."""


def _poem_to_markdown(match: re.Match[str]) -> str:
    inner = _HEADING_RE.sub(lambda m: "#" * int(m.group(1)) + " " + m.group(2).strip(), match.group(1))
    lines = [ln.strip() for seg in _BR_RE.split(inner.strip()) for ln in seg.split("\n") if ln.strip()]
    heads = [ln for ln in lines if ln.startswith("#")]
    verse = [ln for ln in lines if not ln.startswith("#")]
    return "\n\n" + "".join(h + "\n\n" for h in heads) + "\\\n".join(verse) + "\n{.poem}\n\n"


def convert(text: str, name: str) -> str:
    """The published text with raw-HTML poem blocks rewritten; any other raw HTML stops the import."""
    head, sep, body = text.partition("\n---\n")
    if not text.startswith("---\n") or not sep:
        raise ImportError_(f"{name}: no YAML front matter")
    head = _SHORT_YEAR_RE.sub(lambda m: f"date: {int(m.group(1)):04d}-{m.group(2)}-{m.group(3)}", head)
    body = _POEM_RE.sub(_poem_to_markdown, body)
    body = _HEADING_RE.sub(lambda m: "#" * int(m.group(1)) + " " + m.group(2), body)
    leftover = _ANY_TAG_RE.findall(body)
    if leftover:
        raise ImportError_(f"{name}: raw HTML this importer does not know how to convert: {leftover[:3]}")
    return head + sep + body


def plan(old_repo: Path) -> dict[Path, str]:
    """Target path -> file text for everything the old site published."""
    out: dict[Path, str] = {}
    for src_dir, dst_dir in SECTIONS.items():
        folder = old_repo / "src" / "content" / src_dir
        if not folder.is_dir():
            raise ImportError_(f"Missing {folder}")
        for f in sorted(folder.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if _PRIVATE_RE.search(text.split("\n---\n", 1)[0]):
                continue
            out[SITE_ROOT / "content" / dst_dir / f.name] = convert(text, f.name)
    return out


def differences(files: dict[Path, str]) -> list[str]:
    diffs = []
    for dst_dir in SECTIONS.values():
        folder = SITE_ROOT / "content" / dst_dir
        present = {p for p in folder.glob("*.md") if p.name != "_index.md"} if folder.is_dir() else set()
        wanted = {p for p in files if p.parent == folder}
        diffs += [f"missing: {p.relative_to(SITE_ROOT)}" for p in sorted(wanted - present)]
        diffs += [f"extra: {p.relative_to(SITE_ROOT)}" for p in sorted(present - wanted)]
        diffs += [
            f"changed: {p.relative_to(SITE_ROOT)}"
            for p in sorted(wanted & present)
            if p.read_text(encoding="utf-8") != files[p]
        ]
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old_repo", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        files = plan(args.old_repo)
    except ImportError_ as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        diffs = differences(files)
        for d in diffs:
            print(d, file=sys.stderr)
        print(f"legacy content: {len(files)} files, {len(diffs)} differences")
        return 1 if diffs else 0
    for path in differences(files):
        if path.startswith("extra: "):
            (SITE_ROOT / path.removeprefix("extra: ")).unlink()
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    counts = {d: sum(1 for p in files if p.parent.name == d) for d in SECTIONS.values()}
    print("imported " + ", ".join(f"{n} {d}" for d, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
