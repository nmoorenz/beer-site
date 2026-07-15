# beer-site

**Beer Necessities** — a personal beer log. Every beer is a set of photos; everything about it — brewery, name, style, date, rating, notes — is encoded in the photo filenames. No database, no admin screen, no comments, no stars.

Photos live in a private S3 bucket served through CloudFront. The static front-end is hosted on Netlify and reads a single `manifest.json`. It's a standalone AWS stack, independent of any other site. The site is **open** — anyone with the URL can view it.

## How a beer is named

This one convention drives the whole site, so it's worth getting familiar with:

```
20260701-a-1-yeah_garage-project_hapi-daze_pale-ale_notes.jpg
└──────┬─────┘ │ └──┬──┘ └────┬────┘ └───┬───┘ └──┬──┘
   metadata    │  rating   brewery      name    type   notes (freeform, optional)
               └ photo #
```

Split on **underscores** into five fields: `metadata_brewery_name_type_notes`.

- **metadata** splits on **hyphens**: `date-group-photo#-rating`
  - `date` — `YYYYMMDD`
  - `group` — a letter (`a`, `b`, `c`…) so you can log more than one beer on the same day
  - `photo#` — orders photos within a beer (`1`, `2`, `3`…)
  - `rating` — `yeah` 👍 · `eh` 😐 · `nah` 👎
- **brewery / name / type** — hyphens become spaces (`garage-project` → "Garage Project"). Common styles like `ipa`/`apa` stay upper-cased.
- **notes** — freeform, optional, last; hyphens and underscores become spaces.

A **beer** = every photo sharing the same `date-group` (e.g. `20260701-a`), ordered by photo number. The rating and text should be identical across a beer's photos; a mismatch is reported when you sync.

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
├── netlify.toml
├── requirements.txt
├── env.example
└── manifest.json          # local copy (gitignored; source of truth is S3)
```
