# Scripts — everyday use

- **`beer_sync.py`** — the CLI you run from your machine to add beers and update the site.
- **`generate_config.py`** — a Netlify build step (writes `site/config.js` from `BEER_MANIFEST_URL`); you never run it by hand.

Commands run from the repo root and read your `.env`.

## Adding a beer

1. **Name the photos** `date-group-photo#`:

   ```
   20260112-a-1.jpg
   20260112-a-2.jpg     more photos of the same beer — bump the number
   ```

   A second beer on the same day uses the next group letter (`20260112-b-1.jpg`).

2. **Drop them into `photos/`** — flat, no subfolders. They're grouped by the `date-group` prefix.

3. **Add a row to `beers.csv`** with a matching `id`:

   ```
   id,brewery,name,type,abv,size,rating,notes
   20260112-a,Duncan's,Malbec Brett,Wild Sour,8.5,440ml,yeah,
   ```

   `type` is space-separated style words that become filterable `#tags`; `abv` is a number; `rating` is `yeah`/`eh`/`nah`; `notes` is optional.

4. **Check** the join (no AWS, no upload):

   ```bash
   python scripts/beer_sync.py check
   ```

   Prints each beer and flags photos with no CSV row (or rows with no photos). Writes a local `manifest.json` to eyeball.

5. **Sync** — resize, upload, and rebuild the live manifest:

   ```bash
   python scripts/beer_sync.py sync
   ```

   For each photo it makes a ~600px `thumb` (grid) and a ~1600px `full` (lightbox), and uploads both plus the untouched original. Only `thumb` and `full` go in the manifest; the original is archived under `…/orig/` and never served. Photos already in S3 are skipped, so re-running is cheap. The site updates itself.

## Commands

| Command                                 | What it does                                                        | Touches AWS |
| --------------------------------------- | ------------------------------------------------------------------- | ----------- |
| `python scripts/beer_sync.py check`     | Join `photos/` with `beers.csv`, print the beers, write local `manifest.json`. | No |
| `python scripts/beer_sync.py sync`      | Resize + upload new photos, then rebuild and upload the manifest.   | Yes         |
| `python scripts/beer_sync.py manifest`  | Rebuild the manifest from S3 photos + `beers.csv` (no upload).      | Yes         |

## Editing a detail (rating, type, ABV, size, notes, name)

All details live in `beers.csv`, so an edit is a cell change — no photo re-upload and no cache invalidation:

```bash
# edit the cell in beers.csv, then:
python scripts/beer_sync.py manifest
```

The manifest is served uncached, so the change is live on the next page load.

## Replacing an edited photo

The image derivatives are cached for a year, so swapping in an edited photo takes a forced replace plus a cache invalidation. For photo `20260112-a-1` (use your admin profile):

```bash
# 1. delete the three tiers so sync re-uploads them
aws s3 rm s3://YOUR-BUCKET/20260112-a/thumb/20260112-a-1.jpg --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/full/20260112-a-1.jpg  --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/orig/20260112-a-1.jpg  --profile nmoorenz-admin

# 2. make sure the edited file is in photos/, then re-sync
python scripts/beer_sync.py sync

# 3. invalidate CloudFront so the CDN drops the old copy
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/20260112-a/*" --profile nmoorenz-admin
```

`YOUR_DIST_ID` is `terraform output cloudfront_distribution_id`. After it completes, hard-refresh the browser (Ctrl+Shift+R) — a stale image in the tab is usually browser cache, not the CDN.

## Removing a beer

Delete its objects from the S3 bucket and its row from `beers.csv`, then `python scripts/beer_sync.py manifest`. Removing from `photos/` locally alone won't delete them from S3.

## Ratings

`yeah` 👍 · `eh` 😐 · `nah` 👎 — the only valid ratings. Anything else in a row's `rating` cell is reported when you run the CLI.
