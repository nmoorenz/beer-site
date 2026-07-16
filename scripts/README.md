# Scripts — ongoing file management

Two scripts live here. In everyday use you only run one of them.

- **`beer_sync.py`** — the CLI you run from your machine to add beers and update the site.
- **`generate_config.py`** — a Netlify build step you never run by hand (it writes `site/config.js` from `BEER_MANIFEST_URL` at deploy time).

All commands run from the repo root and read your `.env` (set up during infrastructure setup).

## Adding a beer

1. **Name the photos** `date-group-photo#` (see the main [README](../README.md)):

   ```
   20260701-a-1.jpg
   20260701-a-2.jpg     # more photos of the same beer — bump the number
   ```

   A second beer the same day uses the next group letter (`20260701-b-1.jpg`, `-c-`…).

2. **Drop them into `photos/`** — flat, no subfolders. The CLI groups them by the `date-group` prefix.

3. **Add a row to `beers.csv`** with a matching `id`:

   ```
   id,brewery,name,type,abv,size,rating,notes
   20260701-a,Garage Project,Hāpi Daze,Pale Ale,5.8,330ml,yeah,hazy and tropical
   ```

   Open it in Excel or any text editor. `type` is space-separated style words that become filterable `#tags` (`sorbet sour` → #sorbet #sour; hyphenate to keep one together, `west-coast ipa`); `abv` takes a plain number (`5.8`); `rating` is `yeah`/`eh`/`nah`; `notes` is optional.

4. **Preview the join** (no AWS, no upload):

   ```bash
   python scripts/beer_sync.py check
   ```

   Prints each beer, and flags photos with no CSV row (or rows with no photos) — the quick way to catch a mismatched id. Writes a local `manifest.json` you can inspect.

5. **Sync** — resize, upload, and regenerate the live manifest:

   ```bash
   python scripts/beer_sync.py sync
   ```

   For each photo, sync generates two derivatives with Pillow — a ~600px `thumb` (grid) and a ~1600px `full` (lightbox) — and uploads both plus the untouched original. Only `thumb` and `full` go in the manifest; the original is archived under `…/orig/` and never served to the browser, so your full-size shots stay backed up without slowing the site. Photos already synced are skipped, so re-running is cheap. The site updates on its own; nothing to redeploy.

## Commands

| Command                            | What it does                                                        | Touches AWS |
| ---------------------------------- | ------------------------------------------------------------------- | ----------- |
| `python scripts/beer_sync.py check`    | Join `photos/` with `beers.csv`, print the beers, write a local `manifest.json`. | No |
| `python scripts/beer_sync.py sync`     | Upload any new photos to S3, then rebuild and upload the manifest.  | Yes         |
| `python scripts/beer_sync.py manifest` | Rebuild the manifest from S3 photos + `beers.csv` (no upload).      | Yes         |

## Changing something later

Because the details live in `beers.csv`, edits are just cell changes — no renaming photos:

- **Change a rating** (an `eh` you now think is a `nah`): edit that row's `rating` cell, then `sync` (or `manifest`) to rebuild.
- **Fix a typo / add ABV or size**: edit the cell and rebuild. No re-upload of photos needed — use `manifest` if the photos haven't changed.
- **Remove a beer**: delete its objects from the S3 bucket (AWS console or CLI) and its row from `beers.csv`, then run `python scripts/beer_sync.py manifest` to rebuild without it. Removing from `photos/` locally alone won't delete them from S3.

## Ratings

`yeah` 👍 · `eh` 😐 · `nah` 👎 — these three exact words are the only valid ratings. Anything else in a row's `rating` cell is reported when you run the CLI.
