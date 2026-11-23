"""Submit Paper Lanterns URLs to IndexNow (Bing, Yandex, DuckDuckGo, Seznam, Naver -> feeds ChatGPT Search & Copilot).

Standard library only. Requires a public IndexNow verification key file served at
`https://paperlanterns.ink/<key>.txt` (containing only `<key>`). Pass the key via
`--key` or `INDEXNOW_KEY` in `.env` (never hardcode a key here).

Usage:
    python3 scripts/ping_indexnow.py --key <hex-key> --sitemap dist/sitemap.xml --dry-run
    python3 scripts/ping_indexnow.py --key <hex-key> --sitemap dist/sitemap.xml
    python3 scripts/ping_indexnow.py --key <hex-key> --urls https://paperlanterns.ink/ https://paperlanterns.ink/collections/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HOST = "paperlanterns.ink"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH_SIZE = 10000  # IndexNow allows up to 10,000 URLs per POST


def urls_from_sitemap(path: Path) -> list[str]:
    tree = ET.parse(path)
    root = tree.getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [loc.text.strip() for loc in root.iter(f"{ns}loc") if loc.text and loc.text.strip()]


def build_payload(host: str, key: str, urls: list[str]) -> dict[str, object]:
    return {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls,
    }


def submit_batch(host: str, key: str, urls: list[str], *, dry_run: bool = False) -> tuple[int, str]:
    payload = build_payload(host, key, urls)
    body = json.dumps(payload).encode("utf-8")
    if dry_run:
        return 200, f"dry-run: would POST {len(urls)} URL(s) to {ENDPOINT}"
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "PaperLanternsSite/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", default=os.environ.get("INDEXNOW_KEY", ""), help="IndexNow key matching static/<key>.txt")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--sitemap", type=Path, help="Path to built sitemap.xml")
    parser.add_argument("--urls", nargs="*", default=[], help="Explicit URLs to submit")
    parser.add_argument("--dry-run", action="store_true", help="Print batch summary without making network requests")
    args = parser.parse_args(argv)

    if not args.key:
        print("ping_indexnow: pass --key or set INDEXNOW_KEY", file=sys.stderr)
        return 2
    urls: list[str] = []
    if args.sitemap:
        urls.extend(urls_from_sitemap(args.sitemap))
    urls.extend(args.urls)
    urls = list(dict.fromkeys(urls))
    if not urls:
        print("ping_indexnow: no URLs to submit (pass --sitemap or --urls)", file=sys.stderr)
        return 2

    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i : i + BATCH_SIZE]
        status, msg = submit_batch(args.host, args.key, batch, dry_run=args.dry_run)
        print(f"batch {i // BATCH_SIZE + 1}: HTTP {status} ({len(batch)} URLs) {msg}".strip())
        if status not in (200, 202):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
