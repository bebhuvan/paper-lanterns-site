"""Fetch each book's frontispiece plate from the Internet Archive once, for its share card (DECISIONS.md D31).

The plates are committed under assets/og/plates/<book_id>.jpg so builds and tests never need the network.
Run this by hand after a new book with a frontispiece is synced; it skips plates already on disk.
Only archive.org is contacted, and each download is capped in size and checked to be a JPEG.
Standard library only.

Usage:
    python3 scripts/fetch_plates.py            # fetch missing plates
    python3 scripts/fetch_plates.py --check    # exit 1 if a book with a frontispiece has no plate (no network)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1]
BOOKS = SITE_ROOT / "content" / "collections"
PLATES = SITE_ROOT / "assets" / "og" / "plates"
ARCHIVE_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,200}")
MAX_BYTES = 4 * 1024 * 1024
WIDTH = 800


def frontispieces() -> dict[str, tuple[str, int]]:
    """book_id -> (archive_id, leaf) for every book whose record names a frontispiece."""
    found: dict[str, tuple[str, int]] = {}
    for index in sorted(BOOKS.glob("*/_index.md")):
        record, _ = json.JSONDecoder().raw_decode(index.read_text(encoding="utf-8"))
        plate = record.get("frontispiece") or {}
        if "leaf" not in plate:
            continue
        archive_id = record["archive_id"]
        if not ARCHIVE_ID_RE.fullmatch(archive_id):
            raise SystemExit(f"{index}: unexpected archive_id {archive_id!r}")
        found[record["book_id"]] = (archive_id, int(plate["leaf"]))
    return found


def fetch(archive_id: str, leaf: int) -> bytes:
    url = f"https://archive.org/download/{archive_id}/page/n{leaf}_w{WIDTH}.jpg"
    request = urllib.request.Request(url, headers={"User-Agent": "paper-lanterns-site/fetch-plates"})
    with urllib.request.urlopen(request, timeout=60) as response:
        host = urllib.parse.urlparse(response.geturl()).hostname or ""
        if host != "archive.org" and not host.endswith(".archive.org"):
            raise SystemExit(f"{url} redirected off archive.org to {host}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit(f"{url} is larger than {MAX_BYTES} bytes")
    if not data.startswith(b"\xff\xd8\xff"):
        raise SystemExit(f"{url} did not return a JPEG")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a plate is missing; never touches the network")
    args = parser.parse_args(argv)
    missing = [book for book in frontispieces() if not (PLATES / f"{book}.jpg").is_file()]
    if args.check:
        for book in missing:
            print(f"missing share-card plate for {book}: run python3 scripts/fetch_plates.py", file=sys.stderr)
        return 1 if missing else 0
    PLATES.mkdir(parents=True, exist_ok=True)
    books = frontispieces()
    for book in missing:
        archive_id, leaf = books[book]
        data = fetch(archive_id, leaf)
        (PLATES / f"{book}.jpg").write_bytes(data)
        print(f"{book}: {len(data)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
