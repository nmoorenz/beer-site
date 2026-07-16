#!/usr/bin/env python3
"""
beer_sync.py - Beer Necessities CLI tool

Photos are named only enough to identify and order them; everything
descriptive lives in beers.csv. Editing any detail (including ratings) is a
spreadsheet cell change - no renaming.

Filename convention: 20260701-a-1.jpg  = <date YYYYMMDD>-<group letter>-<photo#>
A "beer" = every photo sharing the same date-group prefix (its id), ordered by
photo number.

beers.csv (one row per beer, keyed by id):
    id,brewery,name,type,abv,size,rating,notes
  - id matches the filename prefix exactly (e.g. 20260701-a)
  - type: space-separated style words; each becomes a filter tag
          (e.g. "sorbet sour" -> #sorbet #sour). Hyphenate to keep a
          multi-word tag together (e.g. "west-coast ipa").
  - abv e.g. 5.8 (a trailing % is fine); rating is yeah | eh | nah; notes optional

Photo tiers in S3 (created on sync):
    <id>/thumb/<stem>.jpg   small, for the grid            (in manifest)
    <id>/full/<stem>.jpg    display size, for the lightbox (in manifest)
    <id>/orig/<filename>    untouched original, archived   (NOT in manifest)

Usage:
    python scripts/beer_sync.py sync       # resize + upload + regenerate manifest
    python scripts/beer_sync.py manifest   # regenerate manifest from S3 (no upload)
    python scripts/beer_sync.py check      # join local photos + beers.csv, no AWS
"""

import argparse
import csv
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

BUCKET     = os.environ.get("S3_BUCKET")
REGION     = os.environ.get("AWS_REGION", "ap-southeast-6")
PHOTOS_DIR = Path(os.environ.get("LOCAL_PHOTOS_DIR", "./photos"))
BEERS_CSV  = Path(os.environ.get("BEERS_CSV", "./beers.csv"))

IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VALID_RATINGS = {"yeah", "eh", "nah"}
FILENAME_RE   = re.compile(r"^(\d{8})-([a-z]+)-(\d+)$", re.IGNORECASE)

THUMB_MAX    = 600
FULL_MAX     = 1600
JPEG_QUALITY = 82

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_photo_filename(filename):
    stem = Path(filename).stem
    m = FILENAME_RE.match(stem)
    if not m:
        print(f"WARN: skipping '{filename}': expected <date>-<group>-<photo#>, "
              f"e.g. 20260701-a-1.jpg")
        return None
    date, group, photo_num = m.group(1), m.group(2).lower(), int(m.group(3))
    return f"{date}-{group}", photo_num


def format_date(group_id):
    date = group_id.split("-")[0]
    try:
        d = datetime.strptime(date, "%Y%m%d")
    except ValueError:
        return ""
    return f"{d.day} {MONTHS[d.month]} {d.year}"


def norm_abv(value):
    return value.strip().rstrip("%").strip()


def tags_from_type(type_str):
    """'Sorbet Sour' -> ['sorbet', 'sour']. Split on spaces/commas, lowercased,
    de-duplicated, order preserved. Hyphenate to keep a multi-word tag together,
    e.g. 'west-coast ipa' -> ['west-coast', 'ipa']."""
    seen = []
    for part in re.split(r"[,\s]+", (type_str or "").strip().lower()):
        if part and part not in seen:
            seen.append(part)
    return seen


def load_beers_csv():
    if not BEERS_CSV.exists():
        print(f"ERROR: {BEERS_CSV} not found. Create it with header:", file=sys.stderr)
        print("   id,brewery,name,type,abv,size,rating,notes", file=sys.stderr)
        sys.exit(1)
    rows = {}
    with BEERS_CSV.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"id", "brewery", "name", "type", "abv", "size", "rating", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: {BEERS_CSV} is missing column(s): {sorted(missing)}", file=sys.stderr)
            sys.exit(1)
        for row in reader:
            beer_id = (row.get("id") or "").strip()
            if not beer_id:
                continue
            rating = (row.get("rating") or "").strip().lower()
            if rating not in VALID_RATINGS:
                print(f"WARN: beer {beer_id}: rating '{rating}' is not one of "
                      f"{sorted(VALID_RATINGS)}. Leaving it as-is.")
            rows[beer_id] = {
                "brewery": (row.get("brewery") or "").strip(),
                "name":    (row.get("name") or "").strip(),
                "type":    (row.get("type") or "").strip(),
                "abv":     norm_abv(row.get("abv") or ""),
                "size":    (row.get("size") or "").strip(),
                "rating":  rating,
                "notes":   (row.get("notes") or "").strip(),
            }
    return rows


def _s3():
    import boto3
    if not BUCKET:
        print("ERROR: S3_BUCKET not set in .env", file=sys.stderr)
        sys.exit(1)
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def mime_type(path):
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def resize_jpeg(local_path, max_edge):
    import io
    from PIL import Image, ImageOps
    with Image.open(local_path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()


def put_jpeg(s3, key, data):
    s3.put_object(Bucket=BUCKET, Key=key, Body=data,
                  ContentType="image/jpeg",
                  CacheControl="public, max-age=31536000, immutable")


def base_url():
    return os.environ.get("CLOUDFRONT_URL", f"https://{BUCKET}.s3.{REGION}.amazonaws.com")


def group_photos(filenames):
    groups = defaultdict(list)
    for fn in filenames:
        parsed = parse_photo_filename(fn)
        if parsed:
            group_id, photo_num = parsed
            groups[group_id].append((photo_num, fn))
    return {gid: [fn for _, fn in sorted(items)] for gid, items in groups.items()}


def photo_entry(base, group_id, filename):
    stem = Path(filename).stem
    return {"thumb": f"{base}/{group_id}/thumb/{stem}.jpg",
            "full":  f"{base}/{group_id}/full/{stem}.jpg"}


def build_manifest(groups, meta, base):
    beers = []
    for group_id, filenames in groups.items():
        row = meta.get(group_id)
        if row is None:
            print(f"WARN: {group_id}: {len(filenames)} photo(s) but no row in "
                  f"{BEERS_CSV.name} - skipping. Add an 'id={group_id}' row.")
            continue
        beers.append({
            "id":          group_id,
            "date":        group_id.split("-")[0],
            "dateDisplay": format_date(group_id),
            "brewery":     row["brewery"],
            "name":        row["name"],
            "type":        row["type"],
            "tags":        tags_from_type(row["type"]),
            "abv":         row["abv"],
            "size":        row["size"],
            "rating":      row["rating"],
            "notes":       row["notes"],
            "photos":      [photo_entry(base, group_id, fn) for fn in filenames],
        })
    for beer_id in meta:
        if beer_id not in groups:
            print(f"WARN: {beer_id}: row in {BEERS_CSV.name} but no photos found.")
    beers.sort(key=lambda b: (b["date"], b["id"]), reverse=True)
    counts = {r: sum(1 for b in beers if b["rating"] == r) for r in VALID_RATINGS}
    return {"generated": datetime.now(timezone.utc).isoformat(),
            "counts": {"total": len(beers), **counts},
            "beers": beers}


def report(manifest):
    c = manifest["counts"]
    print(f"\nManifest: {c['total']} beer(s) - yeah {c['yeah']}  eh {c['eh']}  nah {c['nah']}")
    for b in manifest["beers"]:
        abv = f" {b['abv']}%" if b["abv"] else ""
        size = f" {b['size']}" if b["size"] else ""
        tags = " " + " ".join("#" + t for t in b["tags"]) if b["tags"] else ""
        print(f"   - {b['id']}  {b['brewery']} - {b['name']} "
              f"({b['type']}{abv}{size}){tags} [{b['rating']}, {len(b['photos'])} photo(s)]")


def write_manifest_local(manifest):
    Path("./manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def write_manifest_s3(manifest):
    write_manifest_local(manifest)
    s3 = _s3()
    s3.put_object(Bucket=BUCKET, Key="manifest.json",
                  Body=json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
                  ContentType="application/json; charset=utf-8",
                  CacheControl="public, max-age=60")


def scan_local_filenames():
    if not PHOTOS_DIR.exists():
        print(f"ERROR: photos directory not found: {PHOTOS_DIR}", file=sys.stderr)
        sys.exit(1)
    return sorted(p.name for p in PHOTOS_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def cmd_check():
    print(f"\nJoining photos in {PHOTOS_DIR} with {BEERS_CSV} (no upload)\n")
    groups = group_photos(scan_local_filenames())
    manifest = build_manifest(groups, load_beers_csv(), base_url())
    write_manifest_local(manifest)
    report(manifest)


def cmd_sync():
    from botocore.exceptions import ClientError
    s3 = _s3()
    meta = load_beers_csv()
    groups = group_photos(scan_local_filenames())
    print(f"\nSyncing photos from {PHOTOS_DIR} -> s3://{BUCKET}\n")
    uploaded = skipped = 0
    for group_id, group_files in groups.items():
        for fn in group_files:
            stem = Path(fn).stem
            thumb_key = f"{group_id}/thumb/{stem}.jpg"
            full_key = f"{group_id}/full/{stem}.jpg"
            orig_key = f"{group_id}/orig/{fn}"
            local_path = PHOTOS_DIR / fn
            try:
                s3.head_object(Bucket=BUCKET, Key=full_key)
                print(f"   skip {group_id}/{fn} (already synced)")
                skipped += 1
                continue
            except ClientError:
                pass
            print(f"   up   {group_id}/{fn}  (thumb + full + orig) ...", end="", flush=True)
            put_jpeg(s3, thumb_key, resize_jpeg(local_path, THUMB_MAX))
            put_jpeg(s3, full_key, resize_jpeg(local_path, FULL_MAX))
            s3.upload_file(str(local_path), BUCKET, orig_key,
                           ExtraArgs={"ContentType": mime_type(local_path),
                                      "CacheControl": "public, max-age=31536000, immutable"})
            print(" done")
            uploaded += 1
    print(f"\nSync complete: {uploaded} uploaded, {skipped} skipped")
    manifest = build_manifest(groups, meta, base_url())
    write_manifest_s3(manifest)
    report(manifest)


def cmd_manifest():
    s3 = _s3()
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET):
        objects.extend(page.get("Contents", []))
    filenames = []
    for obj in objects:
        parts = obj["Key"].split("/")
        if len(parts) == 3 and parts[1] == "full":
            filenames.append(parts[2])
    groups = group_photos(filenames)
    manifest = build_manifest(groups, load_beers_csv(), base_url())
    write_manifest_s3(manifest)
    report(manifest)


def main():
    parser = argparse.ArgumentParser(description="Beer Necessities CLI")
    parser.add_argument("command", choices=["sync", "manifest", "check"],
                        help="sync: resize + upload + regenerate manifest | "
                             "manifest: regenerate from S3 | "
                             "check: join local photos + beers.csv (no AWS)")
    args = parser.parse_args()
    {"sync": cmd_sync, "manifest": cmd_manifest, "check": cmd_check}[args.command]()


if __name__ == "__main__":
    main()
