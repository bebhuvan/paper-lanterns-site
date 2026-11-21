"""Keep the ledger of published addresses: once the site has served an address, it must keep working.

published-addresses.txt lists every page and download address the site serves, one per line. Addresses are
only ever added. `check` fails when
  - an address in the ledger is no longer served and has no redirect in static/_redirects, or
  - a redirect points at an address the site does not serve, or
  - the site serves an address the ledger does not list yet (run `update` and commit the ledger).
Standard library only.

Usage:
    python3 scripts/addresses.py check  <built-site-dir>
    python3 scripts/addresses.py update <built-site-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1]
LEDGER = SITE_ROOT / "published-addresses.txt"
REDIRECTS = SITE_ROOT / "static" / "_redirects"
HEADER = (
    "# Every address this site serves. Never delete a line: if a page moves, add a redirect in static/_redirects.\n"
    "# Maintained by `python3 scripts/addresses.py update <built-site-dir>`; checked by ./verify.\n"
)
DOWNLOAD_ROOTS = ("collections",)


def served_addresses(public: Path) -> set[str]:
    """Pages (as /path/) and downloadable files under /collections/ in a built site."""
    found: set[str] = set()
    for page in public.rglob("index.html"):
        rel = page.parent.relative_to(public).as_posix()
        found.add("/" if rel == "." else f"/{rel}/")
    for top in DOWNLOAD_ROOTS:
        for f in (public / top).rglob("*") if (public / top).is_dir() else []:
            if f.is_file() and f.name != "index.html":
                found.add("/" + f.relative_to(public).as_posix())
    return found


def read_ledger(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    lines = (ln.strip() for ln in path.read_text(encoding="utf-8").splitlines())
    return {ln for ln in lines if ln and not ln.startswith("#")}


def read_redirects(path: Path) -> dict[str, str]:
    """Cloudflare Pages `_redirects`: `from to [status]` per line, # for comments."""
    rules: dict[str, str] = {}
    if not path.is_file():
        return rules
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("#", 1)[0].split()
        if not parts:
            continue
        if len(parts) not in (2, 3):
            raise ValueError(f"{path.name}:{n}: expected `from to [status]`, got {line!r}")
        rules[parts[0]] = parts[1]
    return rules


def check(public: Path, ledger: Path = LEDGER, redirects: Path = REDIRECTS) -> list[str]:
    served = served_addresses(public)
    listed = read_ledger(ledger)
    rules = read_redirects(redirects)
    problems = [f"published address no longer served and not redirected: {a}" for a in sorted(listed - served - rules.keys())]
    problems += [f"redirect target is not served: {src} -> {dst}" for src, dst in sorted(rules.items()) if dst not in served]
    problems += [
        f"served but not in the ledger (run `python3 scripts/addresses.py update <dir>` and commit): {a}"
        for a in sorted(served - listed)
    ]
    return problems


def update(public: Path, ledger: Path = LEDGER) -> int:
    merged = read_ledger(ledger) | served_addresses(public)
    ledger.write_text(HEADER + "".join(f"{a}\n" for a in sorted(merged)), encoding="utf-8")
    return len(merged)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"check", "update"}:
        print(__doc__, file=sys.stderr)
        return 2
    public = Path(argv[1])
    if argv[0] == "update":
        print(f"addresses: ledger now lists {update(public)} addresses")
        return 0
    try:
        problems = check(public)
    except ValueError as exc:
        print(f"addresses: {exc}", file=sys.stderr)
        return 1
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print(f"addresses: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"addresses: all {len(read_ledger(LEDGER))} published addresses are served or redirected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
