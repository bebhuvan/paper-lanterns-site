"""Copy one edition's Hugo content from the Paper Lanterns pipeline into the site.

The pipeline (`lanterns render-hugo <book_id>`) writes library/<collection>/<book_id>/hugo/ and a manifest.json
listing every page and download file with its SHA-256. This script copies the pages to content/collections/<book_id>/
and the EPUB/Markdown/TEI downloads to static/collections/<book_id>/ (same URL, but Hugo never treats a download as
a page). It checks every hash and replaces both folders wholesale so a removed letter never lingers. It decides
nothing about content. Standard library only.

Usage:
    python3 scripts/sync_from_pipeline.py dostoevsky-family-friends-1914 [--pipeline PATH]
    python3 scripts/sync_from_pipeline.py --check dostoevsky-family-friends-1914   # exit 1 if the site copy is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPELINE = SITE_ROOT.parent / "Paper Lanterns New"
BOOK_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,120}")
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,200}")


class SyncError(RuntimeError):
    """The pipeline output is missing, malformed or does not match its manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_edition_dir(pipeline: Path, book_id: str) -> Path:
    if not BOOK_ID_RE.fullmatch(book_id):
        raise SyncError(f"Not a valid book id: {book_id!r}")
    matches = sorted(p for p in (pipeline / "library").glob(f"*/{book_id}") if (p / "hugo" / "manifest.json").is_file())
    if len(matches) != 1:
        raise SyncError(
            f"Expected exactly one rendered edition for {book_id!r} under {pipeline / 'library'}, found {len(matches)}. "
            f"Run `uv run lanterns render-hugo {book_id}` in the pipeline first."
        )
    return matches[0]


def _safe_name(name: str) -> str:
    if not SAFE_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise SyncError(f"Unsafe file name in manifest: {name!r}")
    return name


Copy = tuple[Path, str, str, str | None]  # (source, "content" or "static", target name, expected sha256 or None)


def plan_copies(edition_dir: Path) -> list[Copy]:
    """Return one Copy for every file the manifest lists."""
    try:
        manifest = json.loads((edition_dir / "hugo" / "manifest.json").read_text(encoding="utf-8"))
        pages = [str(p) for p in manifest["pages"]]
        downloads = [(str(d["from"]), str(d["to"]), str(d["sha256"])) for d in manifest["downloads"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SyncError(f"Unreadable manifest in {edition_dir / 'hugo'}: {exc}") from exc
    if "_index.md" not in pages:
        raise SyncError("Manifest has no _index.md; the book page would be missing")
    copies: list[Copy] = [(edition_dir / "hugo" / _safe_name(p), "content", p, None) for p in pages]
    for rel_from, name, digest in downloads:
        src = (edition_dir / rel_from).resolve()
        if edition_dir.resolve() not in src.parents:
            raise SyncError(f"Download path escapes the edition folder: {rel_from!r}")
        copies.append((src, "static", _safe_name(name), digest))
    for src, _, _, _ in copies:
        if not src.is_file():
            raise SyncError(f"Manifest lists a file that does not exist: {src}")
    return copies


def _dest(site_root: Path, area: str, book_id: str) -> Path:
    return site_root / area / "collections" / book_id


def sync_book(pipeline: Path, book_id: str, site_root: Path = SITE_ROOT) -> Path:
    copies = plan_copies(find_edition_dir(pipeline, book_id))
    with tempfile.TemporaryDirectory(dir=site_root) as tmp:
        for area in ("content", "static"):
            staged = Path(tmp) / area
            staged.mkdir()
            for src, where, name, digest in copies:
                if where != area:
                    continue
                if digest is not None and sha256_file(src) != digest:
                    raise SyncError(f"SHA-256 mismatch for {src}; re-run `lanterns render-hugo` in the pipeline")
                shutil.copyfile(src, staged / name)
        for area in ("content", "static"):
            dest = _dest(site_root, area, book_id)
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(Path(tmp) / area, dest)
    return _dest(site_root, "content", book_id)


def stale_files(pipeline: Path, book_id: str, site_root: Path = SITE_ROOT) -> list[str]:
    """Paths that differ between the pipeline output and the site copy (empty when in sync)."""
    expected = {f"{where}/{name}": src for src, where, name, _ in plan_copies(find_edition_dir(pipeline, book_id))}
    present: set[str] = set()
    for area in ("content", "static"):
        dest = _dest(site_root, area, book_id)
        present |= {f"{area}/{p.name}" for p in dest.iterdir()} if dest.is_dir() else set()
    diffs = sorted(present ^ set(expected))
    for key in sorted(set(expected) & present):
        area, name = key.split("/", 1)
        if sha256_file(expected[key]) != sha256_file(_dest(site_root, area, book_id) / name):
            diffs.append(key)
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("book_id")
    parser.add_argument("--pipeline", type=Path, default=Path(os.environ.get("PL_PIPELINE", DEFAULT_PIPELINE)))
    parser.add_argument("--check", action="store_true", help="Report drift instead of copying")
    args = parser.parse_args(argv)
    try:
        if args.check:
            diffs = stale_files(args.pipeline, args.book_id)
            if diffs:
                print(f"{args.book_id}: site copy differs from pipeline output: {', '.join(diffs[:10])}", file=sys.stderr)
                return 1
            print(f"{args.book_id}: site copy matches pipeline output")
            return 0
        dest = sync_book(args.pipeline, args.book_id)
    except SyncError as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"synced {args.book_id} -> {dest.relative_to(SITE_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
