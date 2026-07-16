# beer-site

**Beer Necessities** — a personal beer log. Every beer is a set of photos named just enough to identify them; all the details — brewery, name, style, ABV, size, rating, notes — live in a single `beers.csv` you edit in Excel or any text editor. No database, no admin screen, no comments, no stars.

Photos live in a private S3 bucket served through CloudFront. The static front-end is hosted on Netlify and reads a single `manifest.json`. It's a standalone AWS stack, independent of any other site. The site is **open** — anyone with the URL can view it.

## How it works: filenames + beers.csv

Two simple pieces. Photo filenames identify and order the shots; `beers.csv` holds everything descriptive.

**Filenames** carry only date, group, and photo number:

```
20260701-a-1.jpg
└──┬───┘ │ └ photo number (orders photos within a beer)
   │     └ group letter (a, b, c … for multiple beers on one day)
   └ date, YYYYMMDD
```

A **beer** = every photo sharing the same `date-group` prefix — its **id**, e.g. `20260701-a`.

**`beers.csv`** has one row per beer, keyed by that id:

```
id,brewery,name,type,abv,size,rating,notes
20260701-a,Garage Project,Hāpi Daze,Pale Ale,5.8,330ml,yeah,hazy and tropical
20260701-b,Epic,Armageddon,IPA,6.66,330ml,nah,
20260703-a,Parrotdog,Birdlife,IPA,5.8,440ml,eh,a bit too bitter for me
```

- `id` matches the filename prefix exactly (`20260701-a`)
- `brewery` / `name` — free text, written how you want it shown
- `type` — space-separated style words; each becomes a filterable `#tag` (e.g. `sorbet sour` → #sorbet #sour). Hyphenate to keep a multi-word tag together (`west-coast ipa` → #west-coast #ipa)
- `abv` — e.g. `5.8` (a trailing `%` is fine; it's added on display)
- `size` — e.g. `330ml`, `440ml`, `pint` (free text)
- `rating` — `yeah` 👍 · `eh` 😐 · `nah` 👎
- `notes` — free text, optional

To change any detail — including a rating — you edit a cell in `beers.csv`; no renaming photos. Photos with no matching row (and rows with no photos) are reported when you sync.

## A note on shell

Command examples in all of these READMEs assume a **POSIX shell** — macOS/Linux, WSL, or **Git Bash** on Windows. If you're in **PowerShell** or **CMD**, most commands work but a few differ:

- Use `python` instead of `python3`, and `copy` instead of `cp`.
- Quote Terraform target addresses: `terraform apply -target="aws_acm_certificate.beer"` (PowerShell can otherwise split the `.beer` off and you'll get `Invalid target "aws_acm_certificate"`).
- `Select-String` replaces `grep`.

## The three READMEs

Detailed docs live next to the thing they describe:

- [`infrastructure/README.md`](infrastructure/README.md) — **one-time setup**: provisioning AWS with Terraform, wiring up Netlify and DNS.
- [`scripts/README.md`](scripts/README.md) — **ongoing use**: naming and adding photos, syncing, changing a rating, removing a beer.
- [`site/README.md`](site/README.md) — the **front-end**: how it loads the manifest, the theme, and previewing locally.

## Layout

```
beer-site/
├── site/                  # static front-end (Netlify) — see site/README.md
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── config.js          # generated at build (gitignored)
├── scripts/               # CLI + build step — see scripts/README.md
│   ├── beer_sync.py
│   └── generate_config.py
├── infrastructure/        # Terraform stack — see infrastructure/README.md
│   ├── main.tf
│   └── terraform.tfvars.example
├── photos/                # local photos to sync (contents gitignored)
├── beers.csv              # the metadata — one row per beer (committed)
├── netlify.toml
├── requirements.txt
├── env.example
└── manifest.json          # local copy (gitignored; source of truth is S3)
```
