#!/usr/bin/env python3
"""
check-beers.py - validate beers.csv against the photos/ folder (no AWS, no deps).

Checks the current schema:

    date,group,photos,brewery,name,type,abv,size,rating,notes

- every required column is present
- each row has a valid `date` (YYYYMMDD) and `group` (letters)
- each date's groups run sequentially from `a` with no gaps (a, b, e is flagged)
- no two rows share the same date+group id
- `rating` is yeah / eh / nah (blank is allowed but counted)
- no photo filename is listed by more than one row

Pass `--photos DIR` to also cross-check the listed filenames against a folder
(every listed file present, no unlisted file left over). This only makes sense
when that folder holds *all* of the photos; a partial local cache will report
every S3-only photo as missing, so it is off by default.

Then prints the distinct ids and a short summary.

Usage (from the repo root):
    python scripts/check-beers.py                      # validate ./beers.csv
    python scripts/check-beers.py --photos ./photos    # also cross-check a folder
"""

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from string import ascii_lowercase
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent   # scripts/ -> repo root

REQUIRED = ["date", "group", "photos", "brewery", "name",
            "type", "abv", "size", "rating", "notes"]
VALID_RATINGS = {"yeah", "eh", "nah"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
GROUP_RE = re.compile(r"^[a-z]+$")


def valid_date(s):
    try:
        datetime.strptime(s, "%Y%m%d")
        return True
    except ValueError:
        return False


def photos_in_folder(folder):
    if not folder.is_dir():
        return None
    return sorted(p.name for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beers", type=Path, default=REPO_ROOT / "beers.csv")
    ap.add_argument("--photos", type=Path, default=None,
                    help="optional folder to cross-check listed photos against")
    args = ap.parse_args()

    if not args.beers.exists():
        print(f"Error: {args.beers} not found.")
        raise SystemExit(1)

    with args.beers.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    problems = []

    missing_cols = [c for c in REQUIRED if c not in fieldnames]
    if missing_cols:
        print(f"Error: beers.csv is missing column(s): {', '.join(missing_cols)}")
        raise SystemExit(1)

    ids = {}
    listed = {}          # filename -> list of ids that list it
    groups_by_date = defaultdict(list)
    blank_rating = 0
    for i, row in enumerate(rows, 2):   # row 2 = first data row
        date = (row.get("date") or "").strip()
        group = (row.get("group") or "").strip()
        rating = (row.get("rating") or "").strip().lower()

        if not date and not group and not (row.get("name") or "").strip():
            continue  # blank line

        if not valid_date(date):
            problems.append(f"row {i}: invalid date {date!r}")
        if not GROUP_RE.match(group):
            problems.append(f"row {i}: invalid group {group!r} (expected letters a, b, c ...)")
        elif valid_date(date):
            groups_by_date[date].append(group)

        beer_id = f"{date}-{group}"
        if beer_id in ids:
            problems.append(f"row {i}: duplicate id {beer_id} (also row {ids[beer_id]})")
        else:
            ids[beer_id] = i

        if rating == "":
            blank_rating += 1
        elif rating not in VALID_RATINGS:
            problems.append(f"row {i} ({beer_id}): invalid rating {rating!r}")

        files = [p.strip() for p in (row.get("photos") or "").split(";") if p.strip()]
        if not files:
            problems.append(f"row {i} ({beer_id}): no photos listed")
        for fn in files:
            listed.setdefault(fn, []).append(beer_id)

    for date in sorted(groups_by_date):
        uniq = sorted(set(groups_by_date[date]))
        expected = list(ascii_lowercase[:len(uniq)])
        if uniq != expected:
            problems.append(f"date {date}: groups not sequential from 'a' "
                            f"(found {','.join(uniq)}, expected {','.join(expected)})")

    for fn, owners in listed.items():
        if len(owners) > 1:
            problems.append(f"photo '{fn}' listed by {len(owners)} rows: {', '.join(owners)}")

    on_disk = []
    if args.photos is not None:
        on_disk = photos_in_folder(args.photos)
        if on_disk is None:
            problems.append(f"photos folder not found: {args.photos} (skipping file cross-check)")
            on_disk = []
        else:
            disk_set = set(on_disk)
            for fn in sorted(listed):
                if fn not in disk_set:
                    problems.append(f"listed photo not in {args.photos}: {fn}")
            for fn in on_disk:
                if fn not in listed:
                    problems.append(f"'{fn}' in {args.photos} but not listed in any row")

    print(f"Checked {len(rows)} row(s) in {args.beers}")
    print()
    if problems:
        print("PROBLEMS FOUND:")
        for p in problems:
            print(f"  {p}")
        print()
        print(f"Found {len(problems)} problem(s).")
    else:
        print("All rows valid; photos and folder are in sync.")

    print()
    print("DISTINCT IDS:")
    for beer_id in sorted(ids):
        print(beer_id)

    print()
    folder_part = f"{len(on_disk)} file(s) in {args.photos}, " if args.photos is not None else ""
    print(f"Summary: {len(ids)} beer(s), {len(listed)} photo(s) listed, "
          f"{folder_part}{blank_rating} blank rating(s).")


if __name__ == "__main__":
    main()
