# Scripts — ongoing file management

Two scripts live here. In everyday use you only run one of them.

- **`beer_sync.py`** — the CLI you run from your machine to add beers and update the site.
- **`generate_config.py`** — a Netlify build step you never run by hand (it writes `site/config.js` from `BEER_MANIFEST_URL` at deploy time).

All commands run from the repo root and read your `.env` (set up during infrastructure setup).

## Adding a beer

1. **Name the photos** per the convention (see the main [README](../README.md)):

   ```
   20260701-a-1-yeah_garage-project_hapi-daze_pale-ale_hazy-and-tropical.jpg
   ```

   Multiple photos of the same beer share the `date-group` and just bump the photo number:

   ```
   20260701-a-1-yeah_garage-project_hapi-daze_pale-ale.jpg
   20260701-a-2-yeah_garage-project_hapi-daze_pale-ale.jpg
   ```

   A second beer the same day uses the next group letter (`-b-`, `-c-`…). Notes are optional — drop the last field if you don't want any.

2. **Drop them into `photos/`** — flat, no subfolders. The CLI groups them for you.

3. **Preview the parse** (no AWS, no upload):

   ```bash
   python scripts/beer_sync.py check
   ```

   This prints each beer it found and writes a local `manifest.json` you can inspect. Anything named wrong is reported and skipped, so this is the quick way to catch typos.

4. **Sync** — upload new photos to S3 and regenerate the live manifest:

   ```bash
   python scripts/beer_sync.py sync
   ```

   The site updates on its own; there's nothing to redeploy. Photos already in S3 are skipped, so re-running is cheap and safe.

## Commands

| Command                            | What it does                                                        | Touches AWS |
| ---------------------------------- | ------------------------------------------------------------------- | ----------- |
| `python scripts/beer_sync.py check`    | Parse the filenames in `photos/`, print the beers, write a local `manifest.json`. | No |
| `python scripts/beer_sync.py sync`     | Upload any new photos to S3, then rebuild and upload the manifest.  | Yes         |
| `python scripts/beer_sync.py manifest` | Rebuild the manifest from what's already in S3 (no upload).         | Yes         |

## Changing something later

Filenames are the single source of truth, so edits mean renaming:

- **Change a rating** (e.g. an `eh` you now think is a `nah`): rename the beer's photo(s) so the rating field reads `nah`, then `sync`. Because the S3 key includes the filename, the renamed files upload as new objects.
- **Fix a typo** in brewery/name/type/notes: rename and `sync` the same way.
- **Remove a beer**: delete its objects from the S3 bucket (via the AWS console or CLI), then run `python scripts/beer_sync.py manifest` to rebuild the manifest without them. Deleting from `photos/` locally alone won't remove them from S3.

> Tip: after renaming to change a rating or text, the old-named objects may linger in S3. Delete the stale ones in the console if you want a tidy bucket, then run `manifest` to refresh.

## Ratings

`yeah` 👍 · `eh` 😐 · `nah` 👎 — these three exact words are the only valid ratings. Anything else in the rating position is reported and the photo is skipped.
