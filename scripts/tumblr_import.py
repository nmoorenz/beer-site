#!/usr/bin/env python3
"""
tumblr_import.py - one-off: turn beer posts from a Tumblr export into candidate
beers.csv rows.

Reads the Tumblr export's posts.csv (post_id, timestamp, tags, text), keeps the
posts tagged `beer`, and for each writes a candidate row in beers.csv shape:

    date,group,photos,brewery,name,type,abv,size,rating,notes,likely_duplicate,caption

- date      from the post timestamp (YYYYMMDD)
- group     a, b, c ... in timestamp order for posts on the same day
- photos    the post's image filenames (from its HTML, in order), copied to staging
- brewery   best-effort: a known brewery name (from beers.csv) found in the caption
- name      the caption with that brewery name removed
- type      any recognised style words among the post's tags
- abv,size  left blank (not in the Tumblr data)
- rating    yeah (these were beers worth posting; change during curation)
- notes     literally "tumblr" (marks the row's source)
- likely_duplicate  yes/no: a fuzzy check of whether this beer's name already
                    appears in beers.csv (advisory only)
- caption   the full Tumblr caption text, so nothing is lost

Nothing is written to beers.csv. Review the candidate CSV, then move accepted
images from the staging dir into photos/ and paste rows into beers.csv.

Usage (from the repo root):
    python scripts/tumblr_import.py --tumblr /path/to/tumblr
"""

import argparse
import csv
import re
import shutil
import string
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent   # scripts/ -> repo root

MEDIA_SRC = re.compile(r'src="[^"]*?/media/([^"]+)"')

STYLE_TAGS = {
    "ipa", "neipa", "apa", "xpa", "pale ale", "pale", "lager", "pilsner", "pils",
    "stout", "porter", "ale", "sour", "gose", "saison", "hazy", "cider", "wheat",
    "hefeweizen", "weizen", "tripel", "dubbel", "red ale", "amber", "brown ale",
    "golden ale", "bitter", "barleywine", "double ipa", "imperial stout", "pale lager",
}

OUT_FIELDS = ["date", "group", "photos", "brewery", "name",
              "type", "abv", "size", "rating", "notes", "likely_duplicate", "caption"]


def dequote(s):
    return (s or "").replace("’", "'").replace("‘", "'") \
                    .replace("“", '"').replace("”", '"')


def norm(s):
    s = dequote(s).lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_breweries(beers_csv):
    out = []
    if beers_csv.exists():
        with beers_csv.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                b = (row.get("brewery") or "").strip()
                if b and b not in out:
                    out.append(b)
    # longest first so "Liberty Brewing Co" beats "Liberty"
    return sorted(out, key=lambda b: -len(b))


def load_names(beers_csv):
    out = []
    if beers_csv.exists():
        with beers_csv.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                nm = norm(row.get("name") or "")
                if len(nm) >= 5:
                    out.append(nm)
    return out


def split_brewery(caption, breweries):
    # Keep the caption's original case; match the brewery case-insensitively.
    orig = " ".join(dequote(caption).split())
    for b in breweries:
        if not b:
            continue
        pat = re.compile(r"\b" + re.escape(b) + r"\b", re.IGNORECASE)
        if pat.search(orig):
            name = " ".join(pat.sub(" ", orig, count=1).split())
            return b, name
    return "", orig


def post_media(html_dir, post_id):
    """Ordered media filenames referenced by a post's HTML."""
    f = html_dir / (post_id + ".html")
    if not f.exists():
        return []
    return MEDIA_SRC.findall(f.read_text(encoding="utf-8"))


def type_from_tags(tags):
    hits = []
    for t in tags:
        tl = norm(t)
        if tl in STYLE_TAGS and tl not in hits:
            hits.append(tl)
    return " ".join(hits)


def looks_duplicate(caption, names):
    cap = norm(caption)
    return any(nm in cap for nm in names)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tumblr", type=Path, required=True,
                    help="path to the Tumblr export (contains posts.csv and download/media)")
    ap.add_argument("--beers", type=Path, default=REPO_ROOT / "beers.csv",
                    help="existing beers.csv (for brewery dictionary + dup check)")
    ap.add_argument("--staging", type=Path, default=REPO_ROOT / "photos" / "tumblr-import",
                    help="where to copy the post images")
    ap.add_argument("--tag", default="beer", help="post tag to select (default: beer)")
    ap.add_argument("--no-copy", action="store_true",
                    help="write the CSV only; don't copy images into the staging dir")
    args = ap.parse_args()

    posts_csv = args.tumblr / "posts.csv"
    media_dir = args.tumblr / "download" / "media"
    html_dir = args.tumblr / "download" / "posts" / "html"
    if not posts_csv.exists():
        raise SystemExit(f"ERROR: {posts_csv} not found")

    breweries = load_breweries(args.beers)
    names = load_names(args.beers)

    with posts_csv.open(newline="", encoding="utf-8") as f:
        posts = [r for r in csv.DictReader(f)
                 if args.tag in [t.strip().lower() for t in (r["tags"] or "").split(";")]]
    posts.sort(key=lambda r: r["timestamp"])

    args.staging.mkdir(parents=True, exist_ok=True)
    per_day = defaultdict(int)
    rows, all_stems = [], []

    for p in posts:
        ts = datetime.fromisoformat(p["timestamp"])
        date = ts.strftime("%Y%m%d")
        group = string.ascii_lowercase[per_day[date]] if per_day[date] < 26 else f"z{per_day[date]}"
        per_day[date] += 1

        stems = post_media(html_dir, p["post_id"])
        all_stems.extend(stems)
        tags = [t.strip() for t in (p["tags"] or "").split(";") if t.strip()]
        brewery, name = split_brewery(p["text"], breweries)
        rows.append({
            "date": date, "group": group, "photos": ";".join(stems),
            "brewery": brewery, "name": name,
            "type": type_from_tags(tags), "abv": "", "size": "", "rating": "yeah",
            "notes": "tumblr",
            "likely_duplicate": "yes" if looks_duplicate(p["text"], names) else "no",
            "caption": " ".join(dequote(p["text"]).split()),
        })

    out_csv = args.staging / "tumblr_candidates.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    dups = sum(1 for r in rows if r["likely_duplicate"] == "yes")
    print(f"{len(rows)} candidate row(s) -> {out_csv}")
    print(f"  flagged likely_duplicate: {dups}  |  not flagged: {len(rows) - dups}")

    # Copy images (resumable: skip ones already staged).
    if args.no_copy:
        print(f"  --no-copy set; {len(all_stems)} image(s) referenced, not copied.")
        return
    copied = skipped = 0
    for s in all_stems:
        dest = args.staging / s
        if dest.exists():
            skipped += 1
            continue
        src = media_dir / s
        if src.exists():
            shutil.copy2(src, dest)
            copied += 1
    print(f"  images: copied {copied}, already present {skipped} (of {len(all_stems)}).")


if __name__ == "__main__":
    main()
