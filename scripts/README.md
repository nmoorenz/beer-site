# Scripts — everyday use

- **`beer_sync.py`** — the CLI you run from your machine to add beers and update the site.
- **`generate_config.py`** — a Netlify build step (writes `site/config.js` from `BEER_MANIFEST_URL`); you never run it by hand.

Commands run from the repo root and read your `.env`. Output has three levels:

- **default** — sync/upload progress (uploaded, skipped) and summaries, without the CSV warnings.
- **`-v` / `--verbose`** — also show CSV warnings (an invalid rating, a photo with no CSV row or a row with no photos) and the full per-beer listing.
- **`-q` / `--quiet`** — only errors and summaries.

## Adding a beer

1. **Name the photos** `date-group-photo#`:

   ```
   20260112-a-1.jpg
   20260112-a-2.jpg     more photos of the same beer — bump the number
   ```

   A second beer on the same day uses the next group letter (`20260112-b-1.jpg`).

2. **Drop them into `photos/`** — flat, no subfolders.

3. **Add a row to `beers.csv`** with a matching `id`:

   ```
   id,brewery,name,type,abv,size,rating,notes
   20260112-a,Duncan's,Malbec Brett,Wild Sour,8.5,440ml,yeah,
   ```

   `type` is space-separated style words that become filterable `#tags`; `abv` is a number; `rating` is `yeah`/`eh`/`nah`; `notes` is optional.

4. **Check** the join offline (no AWS):

   ```bash
   python scripts/beer_sync.py check
   ```

5. **Sync**:

   ```bash
   python scripts/beer_sync.py sync
   ```

   `sync` uploads any new local photos (each as a ~600px `thumb`, a ~1600px `full`, and the untouched original), then rebuilds the manifest from **everything in the bucket** and uploads it. Because it rebuilds from S3, a sync from any computer produces the complete site — it never drops photos uploaded from another machine. The manifest is served uncached, so the site updates immediately.

## Commands

| Command                                | What it does                                                              | Touches AWS |
| -------------------------------------- | ------------------------------------------------------------------------- | ----------- |
| `python scripts/beer_sync.py check`    | Join `photos/` with `beers.csv`, print the beers, write local `manifest.json`. | No     |
| `python scripts/beer_sync.py sync`     | Upload new photos, then rebuild + upload the manifest from all of S3.      | Yes         |
| `python scripts/beer_sync.py download` | Print the bucket size, then pull originals from S3 into `photos/`.         | Yes         |

## Editing a detail (rating, type, ABV, size, notes, name)

Every detail lives in `beers.csv`, so an edit is a cell change — no photo re-upload, no cache invalidation:

```bash
# edit the cell in beers.csv, then:
python scripts/beer_sync.py sync
```

The manifest is served uncached, so the change is live on the next page load.

## Replacing an edited photo

The image derivatives are cached for a year, so swapping in an edited photo takes a forced replace plus a cache invalidation. For photo `20260112-a-1` (use your admin profile):

```bash
aws s3 rm s3://YOUR-BUCKET/20260112-a/thumb/20260112-a-1.jpg --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/full/20260112-a-1.jpg  --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/orig/20260112-a-1.jpg  --profile nmoorenz-admin
python scripts/beer_sync.py sync
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/20260112-a/*" --profile nmoorenz-admin
```

`YOUR_DIST_ID` is `terraform output cloudfront_distribution_id`. After it completes, hard-refresh (Ctrl+Shift+R) — a stale image is usually browser cache, not the CDN.

## Removing a beer

Delete its objects from the S3 bucket and its row from `beers.csv`, then `python scripts/beer_sync.py sync`.

## Setting up another computer

Clone the repo (you get `beers.csv` and `manifest.json`), copy your `.env` across, then pull the photos down from S3:

```bash
python scripts/beer_sync.py download
```

This prints the bucket size first, then downloads every original into `photos/`. To check the size on its own without downloading:

```bash
aws s3 ls s3://YOUR-BUCKET --recursive --summarize --human-readable --profile nmoorenz-admin | tail -2
```

## Committing

`beers.csv` and `manifest.json` are both tracked, so a normal add/commit/push captures the change and gives you a readable diff of what the site now serves:

```bash
git add -A
git commit -m "Add beers"
git push
```

## Ratings

`yeah` 👍 · `eh` 😐 · `nah` 👎 — the only valid ratings. Anything else in a row's `rating` cell is reported when you run the CLI.
