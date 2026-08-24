#!/usr/bin/env python3
"""
beer_sync.py - Beer Necessities CLI tool

Photo filenames carry only identity: 20260112-a-1.jpg = <date>-<group>-<photo#>.
A beer is every photo sharing the same date-group prefix (its id). All the
descriptive detail lives in beers.csv, keyed by that id:

    id,brewery,name,type,abv,size,rating,notes

Photos are stored in S3 in three tiers per beer:
    <id>/thumb/<stem>.jpg   small, for the grid            (in manifest)
    <id>/full/<stem>.jpg    display size, for the lightbox (in manifest)
    <id>/orig/<filename>    untouched original, archived   (NOT in manifest)

Commands:
    python scripts/beer_sync.py sync        # upload new local photos, then rebuild
                                            # manifest from EVERYTHING in S3
    python scripts/beer_sync.py check       # join local photos + beers.csv, no AWS
    python scripts/beer_sync.py download    # pull originals from S3 into ./photos
                                            # (also prints bucket size)

Output levels:
    default       upload/sync progress + summaries (no CSV warnings)
    -v/--verbose  also show CSV warnings (bad rating, no photo/row match) + per-beer listing
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
FILENAME_RE   = re.compile(r"^(\d{8})-([a-z]+)-(\d+)$", re.IGNORECASE)

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


# -- Filename + metadata parsing --------------------------------------------

def parse_photo_filename(filename):
    stem = Path(filename).stem
    m = FILENAME_RE.match(stem)
    if not m:
        warn(f"WARN: skipping '{filename}': expected <date>-<group>-<photo#>, e.g. 20260112-a-1.jpg")
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
                warn(f"WARN: beer {beer_id}: rating '{rating}' is not one of {sorted(VALID_RATINGS)}.")
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
            warn(f"WARN: {group_id}: {len(filenames)} photo(s) but no row in {BEERS_CSV.name} - skipping.")
            continue
        beers.append({
            "id":          group_id,
            "date":        group_id.split("-")[0],
            "year":        group_id[:4],
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
            warn(f"WARN: {beer_id}: row in {BEERS_CSV.name} but no photos found.")
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


def s3_full_filenames(objs):
    # Rebuild from the full-size derivatives: keys look like <id>/full/<stem>.jpg
    out = []
    for o in objs:
        parts = o["Key"].split("/")
        if len(parts) == 3 and parts[1] == "full":
            out.append(parts[2])
    return out


# -- Commands ---------------------------------------------------------------

def cmd_check():
    info(f"\nJoining photos in {PHOTOS_DIR} with {BEERS_CSV} (no upload)\n")
    groups = group_photos(scan_local_filenames())
    manifest = build_manifest(groups, load_beers_csv(), base_url())
    write_manifest_local(manifest)
    report(manifest)


def cmd_sync():
    from botocore.exceptions import ClientError
    s3 = _s3()
    meta = load_beers_csv()

    # 1. upload any new local photos (resized tiers + original)
    local = group_photos(scan_local_filenames())
    uploaded = skipped = 0
    if local:
        info(f"\nSyncing photos from {PHOTOS_DIR} -> s3://{BUCKET}\n")
        for group_id, files in local.items():
            for fn in files:
                stem = Path(fn).stem
                full_key = f"{group_id}/full/{stem}.jpg"
                local_path = PHOTOS_DIR / fn
                try:
                    s3.head_object(Bucket=BUCKET, Key=full_key)
                    info(f"   skip {group_id}/{fn}")
                    skipped += 1
                    continue
                except ClientError:
                    pass
                info(f"   up   {group_id}/{fn}  (thumb + full + orig) ...", end="")
                put_jpeg(s3, f"{group_id}/thumb/{stem}.jpg", resize_jpeg(local_path, THUMB_MAX))
                put_jpeg(s3, full_key, resize_jpeg(local_path, FULL_MAX))
                s3.upload_file(str(local_path), BUCKET, f"{group_id}/orig/{fn}",
                               ExtraArgs={"ContentType": mime_type(local_path),
                                          "CacheControl": "public, max-age=31536000, immutable"})
                info(" done")
                uploaded += 1
        print(f"Uploaded {uploaded}, skipped {skipped}.")
    else:
        info(f"\nNo local photos in {PHOTOS_DIR}; rebuilding manifest from S3 only.")

    # 2. rebuild the manifest from EVERYTHING in S3 (all machines' uploads)
    groups = group_photos(s3_full_filenames(list_objects(s3)))
    manifest = build_manifest(groups, meta, base_url())
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
    s3 = _s3()
    meta = load_beers_csv()
    incoming = [o["Key"] for o in list_objects(s3)
                if o["Key"].startswith("incoming/")
                and Path(o["Key"]).suffix.lower() in IMAGE_EXTS]
    if incoming:
        info(f"\nProcessing {len(incoming)} incoming photo(s)\n")
    processed = 0
    for key in incoming:
        fname = Path(key).name
        parsed = parse_photo_filename(fname)
        if not parsed:
            warn(f"WARN: leaving '{key}' in incoming (name must be <date>-<group>-<photo#>).")
            continue
        group_id = parsed[0]
        stem = Path(fname).stem
        with tempfile.NamedTemporaryFile(suffix=Path(fname).suffix, delete=False) as tf:
            tmp = tf.name
        try:
            s3.download_file(BUCKET, key, tmp)
            info(f"   process {fname} -> {group_id}/ ...", end="")
            put_jpeg(s3, f"{group_id}/thumb/{stem}.jpg", resize_jpeg(Path(tmp), THUMB_MAX))
            put_jpeg(s3, f"{group_id}/full/{stem}.jpg", resize_jpeg(Path(tmp), FULL_MAX))
            s3.copy_object(Bucket=BUCKET, Key=f"{group_id}/orig/{fname}",
                           CopySource={"Bucket": BUCKET, "Key": key},
                           ContentType=mime_type(Path(fname)),
                           CacheControl="public, max-age=31536000, immutable",
                           MetadataDirective="REPLACE")
            s3.delete_object(Bucket=BUCKET, Key=key)
            info(" done")
            processed += 1
        finally:
            os.remove(tmp)
    print(f"Processed {processed} incoming photo(s).")
    groups = group_photos(s3_full_filenames(list_objects(s3)))
    manifest = build_manifest(groups, meta, base_url())
    write_manifest_s3(s3, manifest)
    report(manifest)


def main():
    parser = argparse.ArgumentParser(description="Beer Necessities CLI")
    parser.add_argument("command", choices=["sync", "check", "download", "process-incoming"],
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
