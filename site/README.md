# Site — the front-end

A plain static site: no framework, one small build step. Netlify serves this folder as-is.

## Files

| File         | Role                                                                          |
| ------------ | ----------------------------------------------------------------------------- |
| `index.html` | Markup: header, filter dropdowns, the beer grid, and the detail lightbox.     |
| `style.css`  | The warm beer-hall theme.                                                      |
| `app.js`     | Fetches the manifest and handles filtering, sorting, and the lightbox.        |
| `config.js`  | Written at deploy time by `scripts/generate_config.py`; holds the manifest URL. Gitignored — never edit or commit. |
| `favicon.svg`, `favicon-16/32.png`, `favicon.ico`, `apple-touch-icon.png` | Pint-glass favicon and fallbacks. |

## How it loads

At build time Netlify runs `generate_config.py`, which reads `BEER_MANIFEST_URL` and writes `config.js`:

```js
window.BEER_SITE_CONFIG = { "manifestUrl": "https://cdn.beer.example.com/manifest.json" };
```

`app.js` fetches that manifest and renders everything from it. The manifest is the only data source — the front-end has no knowledge of filenames, the CSV, or S3.

Each beer in the manifest:

```json
{
  "id": "20260112-a",
  "date": "20260112",
  "year": "2026",
  "dateDisplay": "12 Jan 2026",
  "brewery": "Duncan's",
  "name": "Malbec Brett",
  "type": "Wild Sour",
  "tags": ["wild", "sour"],
  "abv": "8.5",
  "size": "440ml",
  "rating": "yeah",
  "notes": "",
  "photos": [
    { "thumb": "https://cdn.beer.example.com/20260112-a/thumb/20260112-a-1.jpg",
      "full":  "https://cdn.beer.example.com/20260112-a/full/20260112-a-1.jpg" }
  ]
}
```

Each photo has a `thumb` (grid) and `full` (lightbox) URL. The untouched original is archived in S3 under `…/orig/` but kept out of the manifest, so the browser never downloads it.

## What the UI does

- **Header** — just the title.
- **Filters** — dropdowns for year, rating, brewery, type, and hashtag, plus a sort (newest / oldest / by brewery). Each option shows a count, e.g. `2025 (13)`, `#ipa (20)`. Filters combine with AND; all client-side, no reload. `year` is used only for filtering and is never shown on a card.
- **Grid** — one card per beer: cover photo, brewery with the month and year (e.g. `Jun 2026`) right-aligned on the same line, name, type · ABV, a rating pill, and a photo-count badge when there's more than one shot. Thumbnails are a uniform 3:4 portrait crop. The grid is paginated at 36 beers per page, with Prev/Next controls at the bottom.
- **Lightbox** — a card opens to a photo carousel (arrow keys, on-screen arrows, dots), then brewery, name, notes, the type / ABV / size / date row, and the `#hashtags`. The card sizes to each photo's aspect ratio, so landscape shots display wider than portraits. `Esc` closes it; empty fields are hidden.

## Theme

Colours and type are CSS variables at the top of `style.css`: amber accent, cream background, warm neutrals; headings in Fraunces, body in Inter (Google Fonts).

## Previewing locally

```bash
# from the repo root
python scripts/beer_sync.py check     # writes ./manifest.json from photos/ + beers.csv
cp manifest.json site/manifest.json   # so the page can fetch it relatively
cd site && python3 -m http.server 8000
# open http://localhost:8000
```

If `config.js` isn't present locally, `app.js` falls back to fetching `manifest.json` next to `index.html`, which is why the copy step works. Remove `site/manifest.json` when done (it's gitignored anyway).
