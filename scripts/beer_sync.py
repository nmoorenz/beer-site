#!/usr/bin/env python3
"""
beer_sync.py - Beer Necessities CLI tool

Photos keep their original filenames. beers.csv maps each beer to its photos:

    date,group,photos,brewery,name,type,abv,size,rating,notes

`date` (8 digits) and `group` (a, b, c ...) together form the beer's id,
<date>-<group> (e.g. 20260112-a), which is the S3 key prefix. The `photos`
column lists a beer's source filenames in display order, separated by ';'
(e.g. img_4821.jpg;img_4822.jpg).

Each beer's photos are stored in S3 in three tiers. The thumb and full tiers use
stable index names derived from the id and the photo's position; the original
keeps its own filename:

    <id>/thumb/<id>-<n>.jpg   small, for the grid            (in manifest)
    <id>/full/<id>-<n>.jpg    display size, for the lightbox (in manifest)
    <id>/orig/<filename>      untouched original, archived   (NOT in manifest)

Commands:
    sync              upload new local photos, then rebuild manifest from all of S3
    check             join local photos + beers.csv, no AWS
    download          pull originals from S3 into ./photos (also prints bucket size)
    process-incoming  turn S3 incoming/ originals into tiers + rebuild (used by CI)

Output levels:
    default       upload/sync progress + summaries (no CSV warnings)
    -v/--verbose  also show CSV warnings (bad rating, photo/row mismatch) + per-beer listing
    -q/--quiet    only errors and summaries

Config: copy env.example to .env and fill in your values.
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
# Tier stems look like <date>-<group>-<n>, e.g. 20260112-a-3
STEM_RE       = re.compile(r"^(\d{8})-([a-z]+)-(\d+)$", re.IGNORECASE)

THUMB_MAX    = 600
FULL_MAX     = 1600
JPEG_QUALITY = 82

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

LEVEL = 1  # 0 = quiet, 1 = normal (default), 2 = verbose


def info(msg, end="\n"):
    if LEVEL >= 1:
        print(msg, end=end, flush=True)


def warn(msg):
    if LEVEL >= 2:
        print(msg, file=sys.stderr)


def detail(msg):
    if LEVEL >= 2:
        print(msg)


def human_size(n):
    x = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if x < 1024:
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{x:.1f} PB"


# -- Metadata parsing -------------------------------------------------------

def format_date(beer_id):
    date = beer_id.split("-")[0]
    try:
        d = datetime.strptime(date, "%Y%m%d")
    except ValueError:
        return ""
    return f"{d.day} {MONTHS[d.month]} {d.year}"


def norm_abv(value):
    return value.strip().rstrip("%").strip()


def tags_from_type(type_str):
    seen = []
    for part in re.split(r"[,\s]+", (type_str or "").strip().lower()):
        if part and part not in seen:
            seen.append(part)
    return seen


def parse_photos_cell(cell):
    return [p.strip() for p in (cell or "").split(";") if p.strip()]


def load_beers_csv():
    if not BEERS_CSV.exists():
        print(f"ERROR: {BEERS_CSV} not found. Create it with header:", file=sys.stderr)
        print("   date,group,photos,brewery,name,type,abv,size,rating,notes", file=sys.stderr)
        sys.exit(1)
    rows = {}
    with BEERS_CSV.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"date", "group", "brewery", "name", "type", "abv", "size", "rating", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: {BEERS_CSV} is missing column(s): {sorted(missing)}", file=sys.stderr)
            sys.exit(1)
        if "photos" not in (reader.fieldnames or []):
            warn("WARN: no 'photos' column in beers.csv - run scripts/beers_migrate.py.")
        for row in reader:
            date = (row.get("date") or "").strip()
            group = (row.get("group") or "").strip()
            if not date or not group:
                continue
            beer_id = f"{date}-{group}"
            rating = (row.get("rating") or "").strip().lower()
            if rating not in VALID_RATINGS:
                warn(f"WARN: beer {beer_id}: rating '{rating}' is not one of {sorted(VALID_RATINGS)}.")
            rows[beer_id] = {
                "brewery": (row.get("brewery") or "").strip(),
                "name":    (row.get("name") or "").strip(),
                "type":    (row.get("type") or "").strip(),
                "abv":     norm_abv(row.get("abv") or ""),
                "size":    (row.get("size") or "").strip(),
                "rating":  rating,
                "notes":   (row.get("notes") or "").strip(),
                "photos":  parse_photos_cell(row.get("photos")),
            }
    return rows


# -- AWS --------------------------------------------------------------------

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


def list_objects(s3):
    objs = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET):
        objs.extend(page.get("Contents", []))
    return objs


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


# -- Grouping / manifest ----------------------------------------------------

def meta_groups(meta):
    """id -> ordered tier stems (<id>-1, <id>-2, ...) from the photos column."""
    out = {}
    for beer_id, row in meta.items():
        n = len(row["photos"])
        if n:
            out[beer_id] = [f"{beer_id}-{i}" for i in range(1, n + 1)]
    return out


def s3_groups(objs):
    """id -> ordered tier stems, rebuilt from the full-tier keys in S3."""
    groups = defaultdict(list)
    for o in objs:
        parts = o["Key"].split("/")
        if len(parts) == 3 and parts[1] == "full":
            stem = Path(parts[2]).stem
            m = STEM_RE.match(stem)
            if m:
                beer_id = f"{m.group(1)}-{m.group(2).lower()}"
                groups[beer_id].append((int(m.group(3)), stem))
    return {bid: [s for _, s in sorted(v)] for bid, v in groups.items()}


def photo_entry(base, beer_id, stem):
    return {"thumb": f"{base}/{beer_id}/thumb/{stem}.jpg",
            "full":  f"{base}/{beer_id}/full/{stem}.jpg"}


def build_manifest(groups, meta, base):
    beers = []
    for beer_id, stems in groups.items():
        row = meta.get(beer_id)
        if row is None:
            warn(f"WARN: {beer_id}: {len(stems)} photo(s) but no row in {BEERS_CSV.name} - skipping.")
            continue
        beers.append({
            "id":          beer_id,
            "date":        beer_id.split("-")[0],
            "year":        beer_id[:4],
            "dateDisplay": format_date(beer_id),
            "brewery":     row["brewery"],
            "name":        row["name"],
            "type":        row["type"],
            "tags":        tags_from_type(row["type"]),
            "abv":         row["abv"],
            "size":        row["size"],
            "rating":      row["rating"],
            "notes":       row["notes"],
            "photos":      [photo_entry(base, beer_id, s) for s in stems],
        })
    for beer_id, row in meta.items():
        if row["photos"] and beer_id not in groups:
            warn(f"WARN: {beer_id}: listed in {BEERS_CSV.name} but no photos found.")
    beers.sort(key=lambda b: (b["date"], b["id"]), reverse=True)
    counts = {r: sum(1 for b in beers if b["rating"] == r) for r in VALID_RATINGS}
    return {"generated": datetime.now(timezone.utc).isoformat(),
            "counts": {"total": len(beers), **counts},
            "beers": beers}


def report(manifest):
    c = manifest["counts"]
    for b in manifest["beers"]:
        abv = f" {b['abv']}%" if b["abv"] else ""
        size = f" {b['size']}" if b["size"] else ""
        detail(f"   - {b['id']}  {b['brewery']} - {b['name']} ({b['type']}{abv}{size}) "
             f"[{b['rating']}, {len(b['photos'])} photo(s)]")
    print(f"Manifest: {c['total']} beer(s) - yeah {c['yeah']}  eh {c['eh']}  nah {c['nah']}")


def write_manifest_local(manifest):
    Path("./manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def write_manifest_s3(s3, manifest):
    write_manifest_local(manifest)
    s3.put_object(Bucket=BUCKET, Key="manifest.json",
                  Body=json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
                  ContentType="application/json; charset=utf-8",
                  CacheControl="public, max-age=60")


def scan_local_filenames():
    if not PHOTOS_DIR.exists():
        return []
    return sorted(p.name for p in PHOTOS_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def validate_local(meta):
    """Warn about listed files missing on disk and local files not listed."""
    local = set(scan_local_filenames())
    listed = set()
    for row in meta.values():
        for fn in row["photos"]:
            listed.add(fn)
            if fn not in local:
                warn(f"WARN: listed photo '{fn}' is not in {PHOTOS_DIR}.")
    for fn in sorted(local - listed):
        warn(f"WARN: '{fn}' is in {PHOTOS_DIR} but not listed in any beers.csv row.")


# -- Commands ---------------------------------------------------------------

def cmd_check():
    info(f"\nJoining photos in {PHOTOS_DIR} with {BEERS_CSV} (no upload)\n")
    meta = load_beers_csv()
    validate_local(meta)
    manifest = build_manifest(meta_groups(meta), meta, base_url())
    write_manifest_local(manifest)
    report(manifest)


def cmd_sync():
    from botocore.exceptions import ClientError
    s3 = _s3()
    meta = load_beers_csv()
    local = set(scan_local_filenames())

    # 1. upload any new local photos (resized tiers + original)
    uploaded = skipped = 0
    info(f"\nSyncing photos from {PHOTOS_DIR} -> s3://{BUCKET}\n")
    for beer_id, row in meta.items():
        for i, fn in enumerate(row["photos"], 1):
            if fn not in local:
                warn(f"WARN: {beer_id}: listed photo '{fn}' not in {PHOTOS_DIR} - skipping.")
                continue
            stem = f"{beer_id}-{i}"
            full_key = f"{beer_id}/full/{stem}.jpg"
            local_path = PHOTOS_DIR / fn
            try:
                s3.head_object(Bucket=BUCKET, Key=full_key)
                info(f"   skip {beer_id}/{fn}")
                skipped += 1
                continue
            except ClientError:
                pass
            info(f"   up   {beer_id}/{fn} -> {stem} (thumb + full + orig) ...", end="")
            put_jpeg(s3, f"{beer_id}/thumb/{stem}.jpg", resize_jpeg(local_path, THUMB_MAX))
            put_jpeg(s3, full_key, resize_jpeg(local_path, FULL_MAX))
            s3.upload_file(str(local_path), BUCKET, f"{beer_id}/orig/{fn}",
                           ExtraArgs={"ContentType": mime_type(local_path),
                                      "CacheControl": "public, max-age=31536000, immutable"})
            info(" done")
            uploaded += 1
    print(f"Uploaded {uploaded}, skipped {skipped}.")

    # 2. rebuild the manifest from EVERYTHING in S3 (all machines' uploads)
    manifest = build_manifest(s3_groups(list_objects(s3)), meta, base_url())
    write_manifest_s3(s3, manifest)
    report(manifest)


def cmd_download():
    s3 = _s3()
    objs = list_objects(s3)
    total = sum(o.get("Size", 0) for o in objs)
    print(f"Bucket {BUCKET}: {len(objs)} objects, {human_size(total)} total")

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = present = 0
    for o in objs:
        parts = o["Key"].split("/")
        if len(parts) == 3 and parts[1] == "orig":
            fn = parts[2]
            dest = PHOTOS_DIR / fn
            if dest.exists():
                present += 1
                continue
            info(f"   down {fn} ...", end="")
            s3.download_file(BUCKET, o["Key"], str(dest))
            info(" done")
            downloaded += 1
    print(f"Downloaded {downloaded} original(s) to {PHOTOS_DIR}; {present} already present.")


def cmd_process_incoming():
    import tempfile
    from botocore.exceptions import ClientError
    s3 = _s3()
    meta = load_beers_csv()
    objs = list_objects(s3)
    incoming = {Path(o["Key"]).name: o["Key"] for o in objs
                if o["Key"].startswith("incoming/")
                and Path(o["Key"]).suffix.lower() in IMAGE_EXTS}
    if incoming:
        info(f"\nProcessing up to {len(incoming)} incoming photo(s)\n")

    processed = 0
    matched = set()
    for beer_id, row in meta.items():
        for i, fn in enumerate(row["photos"], 1):
            key = incoming.get(fn)
            if not key:
                continue
            matched.add(fn)
            stem = f"{beer_id}-{i}"
            full_key = f"{beer_id}/full/{stem}.jpg"
            try:
                s3.head_object(Bucket=BUCKET, Key=full_key)
                s3.delete_object(Bucket=BUCKET, Key=key)  # already processed; clear incoming
                continue
            except ClientError:
                pass
            with tempfile.NamedTemporaryFile(suffix=Path(fn).suffix, delete=False) as tf:
                tmp = tf.name
            try:
                s3.download_file(BUCKET, key, tmp)
                info(f"   process {fn} -> {beer_id}/{stem} ...", end="")
                put_jpeg(s3, f"{beer_id}/thumb/{stem}.jpg", resize_jpeg(Path(tmp), THUMB_MAX))
                put_jpeg(s3, full_key, resize_jpeg(Path(tmp), FULL_MAX))
                s3.copy_object(Bucket=BUCKET, Key=f"{beer_id}/orig/{fn}",
                               CopySource={"Bucket": BUCKET, "Key": key},
                               ContentType=mime_type(Path(fn)),
                               CacheControl="public, max-age=31536000, immutable",
                               MetadataDirective="REPLACE")
                s3.delete_object(Bucket=BUCKET, Key=key)
                info(" done")
                processed += 1
            finally:
                os.remove(tmp)
    for fn, key in incoming.items():
        if fn not in matched:
            warn(f"WARN: leaving '{key}' in incoming (no beers.csv row lists '{fn}').")
    print(f"Processed {processed} incoming photo(s).")

    manifest = build_manifest(s3_groups(list_objects(s3)), meta, base_url())
    write_manifest_s3(s3, manifest)
    report(manifest)


def main():
    parser = argparse.ArgumentParser(description="Beer Necessities CLI")
    parser.add_argument("command",
                        choices=["sync", "check", "download", "process-incoming"],
                        help="sync: upload new photos + rebuild manifest from S3 | "
                             "check: join local photos + beers.csv (no AWS) | "
                             "download: pull originals from S3 into ./photos | "
                             "process-incoming: turn S3 incoming/ originals into tiers + rebuild (used by CI)")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("-q", "--quiet", action="store_true",
                   help="only errors and summaries")
    g.add_argument("-v", "--verbose", action="store_true",
                   help="also show CSV warnings and the per-beer listing")
    args = parser.parse_args()
    global LEVEL
    LEVEL = 0 if args.quiet else (2 if args.verbose else 1)
    {"sync": cmd_sync, "check": cmd_check, "download": cmd_download,
     "process-incoming": cmd_process_incoming}[args.command]()


if __name__ == "__main__":
    main()
