#!/usr/bin/env python3
"""
beers_migrate.py - one-off: convert beers.csv to the date/group/photos schema.

Rewrites beers.csv with columns, in this order:

    date,group,photos,brewery,name,type,abv,size,rating,notes

- Splits the old `id` (<date>-<group>) into separate `date` and `group` columns.
  (Re-running is safe: if the file already has date/group, they are kept.)
- Fills `photos` with each beer's original filenames from S3, ordered by the
  trailing number in the stored filename.
- Leaves `photos` empty when the bucket has no originals for that beer, keeping
  any value already in the row.

Run from the repo root (reads .env, same config as beer_sync.py):

    python scripts/beers_migrate.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

from beer_sync import _s3, list_objects, BEERS_CSV, STEM_RE

NEW_FIELDS = ["date", "group", "photos", "brewery", "name",
              "type", "abv", "size", "rating", "notes"]


def order_key(fn):
    m = STEM_RE.match(Path(fn).stem)
    return (int(m.group(3)) if m else 10 ** 9, fn)


def origs_by_id(s3):
    out = defaultdict(list)
    for o in list_objects(s3):
        parts = o["Key"].split("/")
        if len(parts) == 3 and parts[1] == "orig":
            out[parts[0]].append(parts[2])
    for beer_id in out:
        out[beer_id].sort(key=order_key)
    return out


def row_id(row):
    if (row.get("id") or "").strip():
        return row["id"].strip()
    date = (row.get("date") or "").strip()
    group = (row.get("group") or "").strip()
    return f"{date}-{group}" if date and group else ""


def main():
    if not BEERS_CSV.exists():
        print(f"ERROR: {BEERS_CSV} not found.", file=sys.stderr)
        sys.exit(1)

    origs = origs_by_id(_s3())

    with BEERS_CSV.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    filled = empty = skipped = 0
    for row in rows:
        beer_id = row_id(row)
        if not beer_id or "-" not in beer_id:
            skipped += 1
            continue
        date, _, group = beer_id.partition("-")
        files = origs.get(beer_id, [])
        photos = ";".join(files) if files else (row.get("photos") or "").strip()
        if files:
            filled += 1
        else:
            empty += 1
        out_rows.append({
            "date":    date,
            "group":   group,
            "photos":  photos,
            "brewery": (row.get("brewery") or "").strip(),
            "name":    (row.get("name") or "").strip(),
            "type":    (row.get("type") or "").strip(),
            "abv":     (row.get("abv") or "").strip(),
            "size":    (row.get("size") or "").strip(),
            "rating":  (row.get("rating") or "").strip(),
            "notes":   (row.get("notes") or "").strip(),
        })

    with BEERS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NEW_FIELDS)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    print(f"Rewrote {BEERS_CSV}: {len(out_rows)} row(s); "
          f"photos filled {filled}, empty {empty}"
          + (f", skipped {skipped} row(s) with no id" if skipped else ""))


if __name__ == "__main__":
    main()
