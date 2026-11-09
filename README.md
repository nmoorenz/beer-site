# beer-site

**Beer Necessities** — a personal beer log. Each beer is a set of photos; every detail — and which photos belong to it — lives in a single `beers.csv` you edit in Excel or any text editor. No database, no admin screen, no comments, no stars.

Photos live in a private S3 bucket served through CloudFront. The static front-end is hosted on Netlify and reads a single `manifest.json`. It is a self-contained AWS stack. The site is open — anyone with the URL can view it.

## How it works: beers.csv

`beers.csv` holds one row per beer. Photos keep their original filenames; each row's `photos` column lists them in display order:

```
date,group,photos,brewery,name,type,abv,size,rating,notes
20261101,a,img_20261101153406.jpg,Duncan's,Malbec Brett,Wild Sour,8.5,440ml,yeah,
```

- `date` — the day as 8 digits, `YYYYMMDD`, e.g. `20261101`
- `group` — a letter (`a`, then `b`, `c` … for more than one beer on the same day). `date` and `group` together are the beer's id, `<date>-<group>` (e.g. `20261101-a`), which is the S3 key prefix.
- `photos` — the beer's source filenames, in display order, separated by `;`. The first is the cover photo. Files are never renamed; `sync` stores them under stable `<id>-<n>` names in S3, so the gallery URLs stay clean.
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
├── scripts/               beer_sync.py (CLI), generate_config.py (build step), beers_migrate.py (one-off)
├── infrastructure/        Terraform: S3, CloudFront, ACM, IAM
├── photos/                local photos to sync (contents gitignored)
├── beers.csv              the metadata — one row per beer
├── manifest.json          the generated manifest (committed, so you can diff it)
├── netlify.toml
├── requirements.txt
└── env.example
```
