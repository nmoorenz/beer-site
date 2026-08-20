# beer-site

**Beer Necessities** — a personal beer log. Each beer is a set of photos named just enough to identify them; every detail lives in a single `beers.csv` you edit in Excel or any text editor. No database, no admin screen, no comments, no stars.

Photos live in a private S3 bucket served through CloudFront. The static front-end is hosted on Netlify and reads a single `manifest.json`. It is a self-contained AWS stack. The site is open — anyone with the URL can view it.

## How it works: filenames + beers.csv

Photo filenames carry only date, group, and photo number:

```
20260112-a-1.jpg
   date   | |
          | +-- photo number (orders photos within a beer)
          +---- group letter (a, b, c … for more than one beer on a day)
```

A **beer** is every photo sharing the same `date-group` prefix — its **id**, e.g. `20260112-a`.

`beers.csv` holds one row per beer, keyed by that id:

```
id,brewery,name,type,abv,size,rating,notes
20260112-a,Duncan's,Malbec Brett,Wild Sour,8.5,440ml,yeah,
```

- `id` — matches the filename prefix exactly
- `brewery` / `name` — free text, shown as written
- `type` — space-separated style words; each becomes a filterable `#tag` (`sorbet sour` → #sorbet #sour). Hyphenate to keep a multi-word tag together (`west-coast ipa`)
- `abv` — a number, e.g. `5.8`
- `size` — free text, e.g. `440ml`, `Pint`
- `rating` — `yeah` 👍 · `eh` 😐 · `nah` 👎
- `notes` — free text, optional

## The three READMEs

- [`infrastructure/README.md`](infrastructure/README.md) — one-time AWS, Netlify, and DNS setup.
- [`scripts/README.md`](scripts/README.md) — adding beers, editing details, replacing photos.
- [`site/README.md`](site/README.md) — the front-end.

## Shell

Commands assume a POSIX shell (macOS/Linux, WSL, or Git Bash on Windows). In PowerShell, use `python`/`copy` in place of `python3`/`cp`, quote Terraform targets (`-target="aws_acm_certificate.beer"`), and use `Select-String` for `grep`.

## Layout

```
beer-site/
├── site/                  static front-end served by Netlify
├── scripts/               beer_sync.py (CLI) + generate_config.py (build step)
├── infrastructure/        Terraform: S3, CloudFront, ACM, IAM
├── photos/                local photos to sync (contents gitignored)
├── beers.csv              the metadata — one row per beer
├── netlify.toml
├── requirements.txt
└── env.example
```
