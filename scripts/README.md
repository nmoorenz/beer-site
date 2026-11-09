# Scripts — everyday use

- **`beer_sync.py`** — the CLI you run from your machine to add beers and update the site.
- **`generate_config.py`** — a Netlify build step (writes `site/config.js` from `BEER_MANIFEST_URL`); you never run it by hand.

Commands run from the repo root and read your `.env`. Output has three levels:

- **default** — sync/upload progress (uploaded, skipped) and summaries, without the CSV warnings.
- **`-v` / `--verbose`** — also show CSV warnings (an invalid rating, a listed photo missing from `photos/`, a local file not listed in any row) and the full per-beer listing.
- **`-q` / `--quiet`** — only errors and summaries.

## Adding a beer

1. **Drop the photos into `photos/`** — flat, no subfolders, keep their original filenames (no renaming).

2. **Add a row to `beers.csv`** with the `date`, `group`, and the photo filenames in the `photos` column:

   ```
   date,group,photos,brewery,name,type,abv,size,rating,notes
   20261101,a,img_20261101153406.jpg,Duncan's,Malbec Brett,Wild Sour,8.5,440ml,yeah,
   ```

   `date` is `YYYYMMDD`; `group` is a letter (`a`, then `b`, `c` … for more than one beer on the same day) — together they are the beer's id, `<date>-<group>`. List the `photos` in the order you want them shown, separated by `;` — the first is the cover. `type` is space-separated style words that become filterable `#tags`; `abv` is a number; `rating` is `yeah`/`eh`/`nah`; `notes` is optional.

3. **Check** the join offline (no AWS):

   ```bash
   python scripts/beer_sync.py check
   ```

4. **Sync**:

   ```bash
   python scripts/beer_sync.py sync
   ```

   For each row, `sync` uploads that beer's listed photos (each as a ~600px `thumb` and a ~1600px `full` named `<id>-<n>.jpg`, plus the untouched original under its own filename), then rebuilds the manifest from **everything in the bucket** and uploads it. Because it rebuilds from S3, a sync from any computer produces the complete site — it never drops photos uploaded from another machine. The manifest is served uncached, so the site updates immediately.

## Commands

| Command                                | What it does                                                              | Touches AWS |
| -------------------------------------- | ------------------------------------------------------------------------- | ----------- |
| `python scripts/beer_sync.py check`    | Join `photos/` with `beers.csv` via the `photos` column, flag any mismatches, write local `manifest.json`. | No |
| `python scripts/beer_sync.py sync`     | Upload each row's listed photos, then rebuild + upload the manifest from all of S3. | Yes       |
| `python scripts/beer_sync.py download` | Print the bucket size, then pull originals from S3 into `photos/`.         | Yes         |
| `python scripts/beer_sync.py process-incoming` | Turn S3 `incoming/` originals (matched to rows by the `photos` column) into tiers, then rebuild the manifest (the phone/CI flow). | Yes |

## Filling the photos column from S3

`beers_migrate.py` is a one-off that converts `beers.csv` to the `date,group,photos,brewery,…` schema: it splits the old `id` into `date` and `group`, and fills each beer's `photos` from the originals already in the bucket, ordered by the trailing number in the stored filename:

```bash
python scripts/beers_migrate.py
```

It preserves every other column and leaves a row's `photos` empty when the bucket has no originals for that beer.

## Editing a detail (rating, type, ABV, size, notes, name)

Every detail lives in `beers.csv`, so an edit is a cell change — no photo re-upload, no cache invalidation:

```bash
# edit the cell in beers.csv, then:
python scripts/beer_sync.py sync
```

The manifest is served uncached, so the change is live on the next page load.

## Replacing an edited photo

The image derivatives are cached for a year, so swapping in an edited photo takes a forced replace plus a cache invalidation. For the first photo of `20260112-a` — whose `thumb`/`full` are `20260112-a-1.jpg` and whose original keeps its own filename (e.g. `IMG_4821.jpg`, as listed in that row's `photos` column) — use your admin profile:

```bash
aws s3 rm s3://YOUR-BUCKET/20260112-a/thumb/20260112-a-1.jpg --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/full/20260112-a-1.jpg  --profile nmoorenz-admin
aws s3 rm s3://YOUR-BUCKET/20260112-a/orig/IMG_4821.jpg      --profile nmoorenz-admin
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

`sync` publishes the photos and the manifest straight to S3, so the site is live the moment it finishes — before you commit. `beers.csv` and `manifest.json` are both tracked, so the commit records the change and gives you a readable diff of what the site now serves:

```bash
git add -A
git commit -m "Add beers [skip ci]"
git push
```

The `[skip ci]` tag keeps the GitHub Action from running. The Action does the resize and manifest rebuild for the phone flow; after a `sync` that work is already done, so a push from your computer carries `[skip ci]` and the site stays exactly as `sync` left it.

After a phone update the Action commits a fresh `manifest.json`, so `git pull` before your next computer session to pick it up.

## Updating from your phone (Android)

Edit `beers.csv` in the GitHub mobile app, upload photos to S3 with **S3Drive**, and a GitHub Action does the resize + manifest rebuild.

One-time setup:

- **GitHub:** in the repo, Settings → Secrets and variables → Actions, add `S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CLOUDFRONT_URL` — the same values as your `.env`. Make sure Actions is enabled.
- **Phone:** install S3Drive, add an S3 account (provider AWS, your bucket, region `ap-southeast-6` — or endpoint `s3.ap-southeast-6.amazonaws.com`, the uploader key/secret). Leave S3Drive's own encryption **off** (the Action needs plain files). Bookmark the bucket's `incoming/` folder.

Each beer:

1. Upload the photos to `incoming/` with their original filenames (no renaming).
2. In the GitHub app, add the `beers.csv` row(s), listing those filenames in the `photos` column; commit, push.
3. The Action matches each row's `photos` to the files in `incoming/`, turns them into tiers, rebuilds + uploads the manifest, and commits `manifest.json` back. The site updates in a minute or two.

Upload the photos **before** pushing `beers.csv` so the same run sees both. If they get out of sync, open the repo's Actions tab and hit "Run workflow" (or push a trivial `beers.csv` change).

## Ratings

`yeah` 👍 · `eh` 😐 · `nah` 👎 — the only valid ratings. Anything else in a row's `rating` cell is reported when you run the CLI.
