# Site — the front-end

A plain static site: no framework, no build tooling beyond a one-line config step. Netlify serves this folder as-is.

## Files

| File         | Role                                                                          |
| ------------ | ----------------------------------------------------------------------------- |
| `index.html` | Markup: header + stats, filter/sort controls, the beer grid, and the detail lightbox. |
| `style.css`  | The warm beer-hall theme (see below).                                          |
| `app.js`     | Fetches the manifest, renders the grid, and handles filtering, sorting, and the lightbox. |
| `config.js`  | Generated at deploy time by `scripts/generate_config.py`. Holds the manifest URL. Gitignored — never edit or commit it. |

## How it loads

At build time Netlify runs `generate_config.py`, which reads the `BEER_MANIFEST_URL` environment variable and writes `config.js`:

```js
window.BEER_SITE_CONFIG = { "manifestUrl": "https://cdn.beer.example.com/manifest.json" };
```

On load, `app.js` fetches that manifest and renders everything from it. The manifest is the only data source — the front-end has no knowledge of filenames or S3.

Each beer in the manifest looks like:

```json
{
  "id": "20260701-a",
  "date": "20260701",
  "dateDisplay": "1 Jul 2026",
  "brewery": "Garage Project",
  "name": "Hāpi Daze",
  "type": "Pale Ale",
  "tags": ["pale", "ale"],
  "abv": "5.8",
  "size": "330ml",
  "rating": "yeah",
  "notes": "hazy and tropical",
  "photos": [
    { "thumb": "https://cdn.beer.example.com/20260701-a/thumb/20260701-a-1.jpg",
      "full":  "https://cdn.beer.example.com/20260701-a/full/20260701-a-1.jpg" }
  ]
}
```

Each photo carries a `thumb` (grid) and a `full` (lightbox) URL. The untouched original is archived in S3 under `…/orig/` but deliberately kept out of the manifest, so the browser never downloads it. The CLI builds all this by joining the bucket with `beers.csv`; the front-end only ever sees the manifest — it has no knowledge of filenames, the CSV, or S3.

## What the UI does

- **Header** — just the title. All counts live next to the filter options now.
- **Filters** — dropdowns for year, rating, brewery, type, and hashtag, plus a sort (newest / oldest / by brewery). Each dropdown option shows a count, e.g. `2025 (13)`, `#ipa (20)`. `year` is derived from the date (in the manifest but never shown on a card). All filtering is client-side in `app.js`, combined with AND, no reload.
- **Grid** — one card per beer: cover photo, brewery, name, its `#tags` · ABV, a rating pill, and a photo-count badge when there's more than one shot. Thumbnails are a uniform 3:4 portrait crop (center-cropped); the detail view shows each photo at its true aspect ratio, so portrait and landscape both display fully.
- **Lightbox** — clicking a card opens a detail view with a photo carousel (arrow keys and on-screen arrows, dots for position), the full metadata (style, ABV, size, date), and any notes. `Esc` closes it. Empty fields are hidden.

## Theme

Colours and type are defined as CSS variables at the top of `style.css` — change them there to restyle everything:

- Amber accent, cream background, soft warm neutrals.
- Headings in **Fraunces** (serif), body in **Inter**, both from Google Fonts.

## Previewing locally

The front-end is just static files, so any local server works. To see it with real data, first generate a local manifest, then point the site at it:

```bash
# from the repo root
python scripts/beer_sync.py check     # writes ./manifest.json from photos/
cp manifest.json site/manifest.json   # so the page can fetch it relatively
cd site && python3 -m http.server 8000
# open http://localhost:8000
```

If `config.js` isn't present locally (it's only generated at deploy), `app.js` falls back to fetching `manifest.json` next to `index.html` — which is why the copy step above works. Remove `site/manifest.json` when you're done so it isn't committed.
