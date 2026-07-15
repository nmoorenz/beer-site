#!/usr/bin/env python3
"""
beer_sync.py — Beer Necessities CLI tool

Everything about a beer is encoded in its photo filenames. There is no
separate metadata file to maintain — you name the photos, the CLI does the
rest.

Filename convention
-------------------
    20260701-a-1-yeah_garage-project_hapi-daze_pale-ale_notes.jpg

Split on UNDERSCORES into 5 fields:

    <metadata>_<brewery>_<name>_<type>_<notes>.ext

  1. metadata  — split on HYPHENS: <date>-<group>-<photo#>-<rating>
                   date    YYYYMMDD          e.g. 20260701
                   group   a letter          groups a beer; a, b, c ... for
                                             multiple beers on the same day
                   photo#  1, 2, 3 ...       orders photos within one beer
                   rating  yeah | eh | nah   thumbs up / neutral / thumbs down
  2. brewery   — hyphens become spaces  ->  "garage project"
  3. name      — hyphens become spaces  ->  "hapi daze"
  4. type      — hyphens become spaces  ->  "pale ale"
  5. notes     — freeform, OPTIONAL, may contain underscores; hyphens -> spaces

A "beer" = every photo sharing the same <date>-<group> (e.g. 20260701-a).
Photos are ordered by photo number. The rating/brewery/name/type/notes are
taken from the beer's photos (they should match across a beer's photos; a
mismatch is reported as a warning).

Usage
-----
    python scripts/beer_sync.py sync       # upload photos to S3 + regenerate manifest
    python scripts/beer_sync.py manifest   # regenerate manifest from S3 (no upload)
    python scripts/beer_sync.py check      # parse local filenames + print, no AWS calls

Config: copy env.example to .env and fill in your values.
"""

import argparse
import json
import mimetypes
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

BUCKET     = os.environ.get("S3_BUCKET")
REGION     = os.environ.get("AWS_REGION", "ap-southeast-6")
PHOTOS_DIR = Path(os.environ.get("LOCAL_PHOTOS_DIR", "./photos"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VALID_RATINGS = {"yeah", "eh", "nah"}
DATE_RE = re.compile(r"^\d{8}$")

# Words that should stay upper-cased when humanising hyphenated fields.
ACRONYMS = {
    "ipa", "neipa", "apa", "dipa", "tipa", "xpa", "ipl", "esb", "abv",
    " npa", "wcipa", "diipa", "gf", "nz", "usa", "uk",
}

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Filename parsing (no AWS needed) ───────────────────────────────────────────

def humanise(text: str) -> str:
    """Hyphens -> spaces; title-case words, keeping known acronyms upper."""
    words = text.split("-")
    out = []
    for w in words:
        if not w:
            continue
        out.append(w.upper() if w.lower() in ACRONYMS else w[:1].upper() + w[1:])
    return " ".join(out)


def humanise_notes(text: str) -> str:
    """Notes: hyphens -> spaces, underscores -> spaces, no title-casing."""
    return text.replace("-", " ").replace("_", " ").strip()


def format_date(yyyymmdd: str) -> str:
    """20260701 -> '1 Jul 2026'. Returns '' if unparseable."""
    if not DATE_RE.match(yyyymmdd):
        return ""
    try:
        d = datetime.strptime(yyyymmdd, "%Y%m%d")
    except ValueError:
        return ""
    return f"{d.day} {MONTHS[d.month]} {d.year}"


def parse_filename(filename: str) -> dict | None:
    """Parse one photo filename into its fields. Returns None if it doesn't
    match the convention (with a warning printed)."""
    stem = Path(filename).stem
    parts = stem.split("_")

    if len(parts) < 4:
        print(f"⚠️  Skipping '{filename}': expected at least "
              f"<meta>_<brewery>_<name>_<type>, got {len(parts)} field(s).")
        return None

    meta, brewery, name, beer_type = parts[0], parts[1], parts[2], parts[3]
    notes_raw = "_".join(parts[4:]) if len(parts) > 4 else ""

    meta_parts = meta.split("-")
    if len(meta_parts) != 4:
        print(f"⚠️  Skipping '{filename}': metadata field '{meta}' must be "
              f"<date>-<group>-<photo#>-<rating>.")
        return None

    date, group, photo_num, rating = meta_parts

    if not DATE_RE.match(date):
        print(f"⚠️  Skipping '{filename}': date '{date}' must be YYYYMMDD.")
        return None
    if not photo_num.isdigit():
        print(f"⚠️  Skipping '{filename}': photo number '{photo_num}' must be numeric.")
        return None
    if rating not in VALID_RATINGS:
        print(f"⚠️  Skipping '{filename}': rating '{rating}' must be one of "
              f"{sorted(VALID_RATINGS)}.")
        return None

    return {
        "group_id":  f"{date}-{group}",
        "date":      date,
        "group":     group,
        "photo_num": int(photo_num),
        "rating":    rating,
        "brewery":   humanise(brewery),
        "name":      humanise(name),
        "type":      humanise(beer_type),
        "notes":     humanise_notes(notes_raw),
        "filename":  filename,
    }


def group_beers(parsed: list[dict]) -> list[dict]:
    """Group parsed photos into beers keyed by group_id, newest first."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in parsed:
        groups[p["group_id"]].append(p)

    beers = []
    for group_id, photos in groups.items():
        photos.sort(key=lambda x: x["photo_num"])
        first = photos[0]

        # Warn on inconsistent metadata within a beer.
        for field in ("rating", "brewery", "name", "type"):
            values = {p[field] for p in photos}
            if len(values) > 1:
                print(f"⚠️  Beer {group_id}: inconsistent {field} across photos "
                      f"({sorted(values)}). Using '{first[field]}'.")

        beers.append({
            "id":          group_id,
            "date":        first["date"],
            "dateDisplay": format_date(first["date"]),
            "brewery":     first["brewery"],
            "name":        first["name"],
            "type":        first["type"],
            "rating":      first["rating"],
            "notes":       first["notes"],
            "photos":      [p["filename"] for p in photos],
        })

    # Newest first: sort by date desc, then group letter desc.
    beers.sort(key=lambda b: (b["date"], b["id"]), reverse=True)
    return beers


# ── AWS (imported lazily so `check` works without boto3/creds) ──────────────────

def _s3():
    import boto3
    if not BUCKET:
        print("❌  S3_BUCKET not set in .env", file=sys.stderr)
        sys.exit(1)
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def base_url() -> str:
    return os.environ.get("CLOUDFRONT_URL", f"https://{BUCKET}.s3.{REGION}.amazonaws.com")


# ── Local scan ──────────────────────────────────────────────────────────────

def scan_local() -> list[dict]:
    if not PHOTOS_DIR.exists():
        print(f"❌  Photos directory not found: {PHOTOS_DIR}", file=sys.stderr)
        sys.exit(1)
    files = sorted(
        p.name for p in PHOTOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    parsed = [r for r in (parse_filename(f) for f in files) if r]
    return parsed


# ── Manifest ──────────────────────────────────────────────────────────────────

def build_manifest(beers: list[dict], base: str) -> dict:
    """Turn beers (with bare filenames) into a manifest with full CDN URLs.
    Photos are stored in S3 under <group_id>/<filename>."""
    out_beers = []
    for b in beers:
        b = dict(b)
        b["photos"] = [f"{base}/{b['id']}/{fn}" for fn in b["photos"]]
        out_beers.append(b)

    counts = {r: sum(1 for b in out_beers if b["rating"] == r) for r in VALID_RATINGS}
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "counts":    {"total": len(out_beers), **counts},
        "beers":     out_beers,
    }


def write_manifest(manifest: dict, upload: bool) -> None:
    json_str = json.dumps(manifest, indent=2, ensure_ascii=False)
    Path("./manifest.json").write_text(json_str, encoding="utf-8")
    if upload:
        s3 = _s3()
        s3.put_object(
            Bucket=BUCKET,
            Key="manifest.json",
            Body=json_str.encode("utf-8"),
            ContentType="application/json; charset=utf-8",
            CacheControl="public, max-age=60",
        )
    c = manifest["counts"]
    print(f"\n✅  Manifest: {c['total']} beer(s) — 👍 {c['yeah']}  😐 {c['eh']}  👎 {c['nah']}")
    for b in manifest["beers"]:
        print(f"   🍺 {b['id']}  {b['brewery']} — {b['name']} ({b['type']}) "
              f"[{b['rating']}, {len(b['photos'])} photo(s)]")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check() -> None:
    """Parse local filenames and print the resulting beers. No AWS calls."""
    print(f"\n🔎 Parsing filenames in {PHOTOS_DIR} (no upload)\n")
    beers = group_beers(scan_local())
    if not beers:
        print("No valid beer photos found.")
        return
    manifest = build_manifest(beers, base_url())
    write_manifest_local_only(manifest)


def write_manifest_local_only(manifest: dict) -> None:
    Path("./manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    c = manifest["counts"]
    print(f"✅  Wrote local manifest.json: {c['total']} beer(s) — "
          f"👍 {c['yeah']}  😐 {c['eh']}  👎 {c['nah']}")
    for b in manifest["beers"]:
        print(f"   🍺 {b['id']}  {b['brewery']} — {b['name']} ({b['type']}) "
              f"[{b['rating']}, {len(b['photos'])} photo(s)]")


def cmd_sync() -> None:
    """Upload any new local photos to S3, then regenerate the manifest."""
    from botocore.exceptions import ClientError

    s3 = _s3()
    parsed = scan_local()
    beers = group_beers(parsed)
    if not beers:
        print("No valid beer photos to sync.")
        return

    print(f"\n🔄 Syncing photos from {PHOTOS_DIR} → s3://{BUCKET}\n")
    uploaded = skipped = 0

    for p in parsed:
        s3_key = f"{p['group_id']}/{p['filename']}"
        local_path = PHOTOS_DIR / p["filename"]
        try:
            s3.head_object(Bucket=BUCKET, Key=s3_key)
            print(f"   ⏭  {s3_key} (already exists)")
            skipped += 1
            continue
        except ClientError:
            pass
        print(f"   ⬆  {s3_key} ...", end="", flush=True)
        s3.upload_file(
            str(local_path), BUCKET, s3_key,
            ExtraArgs={
                "ContentType": mime_type(local_path),
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
        print(" done")
        uploaded += 1

    print(f"\n✅  Sync complete: {uploaded} uploaded, {skipped} skipped")
    write_manifest(build_manifest(beers, base_url()), upload=True)


def cmd_manifest() -> None:
    """Regenerate the manifest from what's currently in S3 (no upload)."""
    s3 = _s3()
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET):
        objects.extend(page.get("Contents", []))

    parsed = []
    for obj in objects:
        parts = obj["Key"].split("/")
        if len(parts) != 2:
            continue
        _group, filename = parts
        if Path(filename).suffix.lower() not in IMAGE_EXTS:
            continue
        r = parse_filename(filename)
        if r:
            parsed.append(r)

    beers = group_beers(parsed)
    write_manifest(build_manifest(beers, base_url()), upload=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Beer Necessities CLI")
    parser.add_argument(
        "command",
        choices=["sync", "manifest", "check"],
        help="sync: upload + regenerate manifest | manifest: regenerate from S3 | "
             "check: parse local filenames only (no AWS)",
    )
    args = parser.parse_args()

    {"sync": cmd_sync, "manifest": cmd_manifest, "check": cmd_check}[args.command]()


if __name__ == "__main__":
    main()
