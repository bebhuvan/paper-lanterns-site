"""Build data/decades.json and data/people.json from the content this site already holds.

Hugo makes pages only from content, so the Explore (by decade) and People pages are generated from these two
small files by content adapters (content/explore/_content.gotmpl, content/people/_content.gotmpl). Nothing here
is invented: every entry comes from synced pipeline front matter or the old site's hand-curated front matter.

  decades.json  one entry per decade that has at least one dated letter: its letters, as page paths.
  people.json   people as the volumes credit them (`authors` in book data, role kept exactly as recorded, e.g.
                "(tr.)") and the writers named on hand-curated pages. A collection letter counts towards a
                person only when its signed name, or its full name from the pipeline's edition.toml, equals the
                credited name exactly.

Usage:
    python3 scripts/build_indexes.py          # write
    python3 scripts/build_indexes.py --check  # exit 1 if the files are stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1]
CONTENT = SITE_ROOT / "content"
CURATED = ("letters", "essays", "lectures", "speeches")
SAME_PERSON = SITE_ROOT / "data" / "people-same-person.json"
_ROLE_RE = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<role>[^()]*)\)\s*$")
_DATE_RE = re.compile(r"^date:\s*\"?(\d{1,4})-(\d{2})-(\d{2})", re.M)
_AUTHOR_RE = re.compile(r"^author:\s*\n\s+name:\s*\"?(?P<name>[^\"\n]+?)\"?\s*$", re.M)
_TITLE_RE = re.compile(r"^title:\s*\"?(?P<title>[^\"\n]+?)\"?\s*$", re.M)


class IndexError_(RuntimeError):
    """Content is missing a field these indexes need."""


def slugify(name: str) -> str:
    flat = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", flat).strip("-")


def split_credit(credit: str) -> tuple[str, str]:
    """'Ethel Colburn Mayne (tr.)' -> ('Ethel Colburn Mayne', 'tr.'); a plain name has no role."""
    m = _ROLE_RE.match(credit.strip())
    return (m.group("name").strip(), m.group("role").strip()) if m else (credit.strip(), "")


def read_collections() -> tuple[list[dict], list[dict]]:
    books, letters = [], []
    for index in sorted((CONTENT / "collections").glob("*/_index.md")):
        book = json.loads(index.read_text(encoding="utf-8"))
        books.append(book)
        for f in sorted(index.parent.glob("[0-9]*.md"), key=lambda p: int(p.stem)):
            fm = json.loads(f.read_text(encoding="utf-8"))
            letters.append(
                {
                    "path": f"/collections/{book['book_id']}/{f.stem}",
                    "book_id": book["book_id"],
                    "iso": fm["letter_date"]["iso"],
                    "names": {n for n in (fm.get("sender_full"), fm.get("sender")) if n},
                }
            )
    return books, letters


def read_curated() -> list[dict]:
    items = []
    for section in CURATED:
        for f in sorted((CONTENT / section).glob("*.md")):
            if f.name == "_index.md":
                continue
            head = f.read_text(encoding="utf-8").split("\n---\n", 1)[0]
            author, date, title = _AUTHOR_RE.search(head), _DATE_RE.search(head), _TITLE_RE.search(head)
            if not (author and title):
                raise IndexError_(f"{f}: front matter needs title and author.name")
            items.append(
                {
                    "path": f"/{section}/{f.stem}",
                    "section": section,
                    "author": author.group("name").strip(),
                    "year": int(date.group(1)) if date else None,
                }
            )
    return items


def build_decades(letters: list[dict], curated: list[dict]) -> list[dict]:
    by_decade: dict[int, dict] = defaultdict(lambda: {"collection_letters": defaultdict(list), "curated": []})
    for lt in letters:
        if lt["iso"]:
            by_decade[int(lt["iso"][:4]) // 10 * 10]["collection_letters"][lt["book_id"]].append(lt["path"])
    for item in curated:
        if item["section"] == "letters" and item["year"] is not None:
            by_decade[item["year"] // 10 * 10]["curated"].append(item["path"])
    out = []
    for decade in sorted(by_decade):
        entry = by_decade[decade]
        books = [{"book_id": b, "paths": p} for b, p in sorted(entry["collection_letters"].items())]
        count = sum(len(b["paths"]) for b in books) + len(entry["curated"])
        out.append({"decade": decade, "slug": f"{decade}s", "count": count, "books": books, "curated": entry["curated"]})
    return out


def build_people(books: list[dict], letters: list[dict], curated: list[dict], same: dict[str, str] | None = None) -> list[dict]:
    people: dict[str, dict] = {}
    joined = same or {}

    def person(name: str) -> dict:
        name = joined.get(name, name)
        entry = people.setdefault(name, {"name": name, "slug": slugify(name), "credits": [], "curated": [], "letters": {}, "also": []})
        return entry

    for book in books:
        for credit in book.get("authors") or []:
            name, role = split_credit(credit)
            person(name)["credits"].append({"book_id": book["book_id"], "role": role})
    for item in curated:
        person(item["author"])["curated"].append(item["path"])
    for form, name in sorted(joined.items()):
        if name in people:
            people[name]["also"].append(form)
    for lt in letters:
        names = {joined.get(n, n) for n in lt["names"]}
        for name in names & people.keys():
            counts = people[name]["letters"]
            counts[lt["book_id"]] = counts.get(lt["book_id"], 0) + 1
    slugs: dict[str, str] = {}
    for p in people.values():
        if not p["slug"] or p["slug"] in slugs:
            raise IndexError_(f"Person {p['name']!r} has an empty or duplicate address slug {p['slug']!r}")
        slugs[p["slug"]] = p["name"]
    return sorted(people.values(), key=lambda p: p["slug"])


def read_same_person() -> dict[str, str]:
    raw = json.loads(SAME_PERSON.read_text(encoding="utf-8")) if SAME_PERSON.is_file() else {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def render() -> dict[Path, str]:
    books, letters = read_collections()
    curated = read_curated()
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"  # noqa: E731
    return {
        SITE_ROOT / "data" / "decades.json": dump(build_decades(letters, curated)),
        SITE_ROOT / "data" / "people.json": dump(build_people(books, letters, curated, read_same_person())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        files = render()
    except (IndexError_, KeyError, ValueError) as exc:
        print(f"build_indexes failed: {exc}", file=sys.stderr)
        return 1
    stale = [p for p, text in files.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(SITE_ROOT)} (run python3 scripts/build_indexes.py)", file=sys.stderr)
        return 1 if stale else 0
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    print("indexes: " + ", ".join(f"{p.name} {len(json.loads(t))} entries" for p, t in files.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
