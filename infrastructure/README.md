# Infrastructure — one-time setup

Terraform provisions a standalone AWS stack for beer-site: a private S3 bucket, a CloudFront distribution to serve it, an ACM certificate, CloudFront Origin Access Control, and an IAM user the CLI uses to upload. Nothing here is shared with any other site.

You only run this once (plus the odd `terraform apply` if you change something). Day-to-day photo management doesn't touch Terraform — see [`../scripts/README.md`](../scripts/README.md).

## What gets created

- **S3 bucket** — fully private (all public access blocked). Stores photos and `manifest.json`. Direct S3 URLs return 403.
- **CloudFront + OAC** — the only thing allowed to read the bucket, via SigV4 signing. Serves everything over `cdn.beer.example.com`. Photos cache for a year; `manifest.json` is set to never cache so updates show immediately.
- **ACM certificate** — the TLS cert for the CDN subdomain. Must live in `us-east-1` (a CloudFront requirement), which the second provider alias in `main.tf` handles.
- **IAM uploader user** — a scoped user with put/get/delete/list on the bucket. Its keys go in `.env` for the CLI.

## Prerequisites

- Python 3.10+
- [Terraform](https://developer.hashicorp.com/terraform/install)
- [AWS CLI](https://aws.amazon.com/cli/)
- An AWS account and a Netlify account

> Requires a recent AWS Terraform provider — the `ap-southeast-6` (New Zealand) region is only recognised by newer versions, so `main.tf` pins `~> 6.0`.

```bash
pip install -r ../requirements.txt
aws configure --profile your-aws-profile
```

## Steps

> **Shell:** these commands assume a POSIX shell (macOS/Linux, WSL, or Git Bash on Windows). In **PowerShell**, quote the Terraform `-target` value as shown below, and use `python`/`copy` in place of `python3`/`cp`. See the [shell note](../README.md#a-note-on-shell) in the main README.

### 1. Configure variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

| Variable          | What to set                                                  |
| ----------------- | ------------------------------------------------------------ |
| `bucket_name`     | A globally-unique S3 bucket name, e.g. `nmoore-beer-photos`  |
| `aws_region`      | Your region, e.g. `ap-southeast-6` (Asia Pacific, New Zealand) |
| `aws_profile`     | The AWS CLI profile you configured above                     |
| `cdn_domain`      | The CDN subdomain, e.g. `cdn.beer.nmoore.nz`                 |
| `allowed_origins` | Your site origin(s), e.g. `["https://beer.nmoore.nz"]`       |

### 2. Create and validate the certificate first

CloudFront won't build until the certificate is validated, so do the cert on its own:

```bash
terraform init
terraform apply -target="aws_acm_certificate.beer"
terraform output acm_certificate_validation_options
```

`acm_certificate_validation_options` prints a validation record — ACM's way of confirming you control the domain before it issues a certificate. It gives you three fields — add these as a CNAME record in your DNS provider:

| Field    | Looks like                          | Goes in the registrar's…       |
| -------- | ----------------------------------- | ------------------------------ |
| name     | `_a1b2c3….cdn.beer.example.com`     | Host / Name                    |
| type     | `CNAME`                             | Record type                    |
| value    | `_x7y8z9….acm-validations.aws.`     | Value / Points to              |

You don't click anything to validate — ACM polls DNS and flips the certificate to **Issued** on its own once the CNAME resolves. Check status in the ACM console in region **us-east-1** (CloudFront only accepts certs from there, regardless of your bucket's region). Usually 5–10 minutes, occasionally longer if DNS is slow to propagate.

Or check from the CLI:

```bash
aws acm list-certificates --region us-east-1
aws acm describe-certificate --region us-east-1 --certificate-arn <arn> --query "Certificate.Status"
```

> **Leave the validation CNAME in place permanently.** ACM reuses it to auto-renew the certificate each year — delete it and renewal silently fails later.

### 3. Provision the rest

```bash
terraform apply
```

This creates the bucket, CloudFront distribution, bucket policy, OAC, and IAM uploader.

### 4. Point DNS at CloudFront

```bash
terraform output cloudfront_domain     # e.g. d123abcd.cloudfront.net
```

At your registrar, add a CNAME for `cdn.beer.example.com` → that CloudFront domain.

### 5. Fill in the CLI's `.env`

```bash
cp ../env.example ../.env
```

Fill it from the Terraform outputs:

```bash
terraform output bucket_name
terraform output uploader_access_key_id
terraform output uploader_secret_access_key
terraform output manifest_url
```

Set `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `CLOUDFRONT_URL` (the base CDN URL, e.g. `https://cdn.beer.example.com`).

### 6. Connect Netlify

Connect the repo in Netlify with:

| Setting           | Value                                                                  |
| ----------------- | ---------------------------------------------------------------------- |
| Publish directory | `site`                                                                 |
| Build command     | `pip install -r requirements.txt && python scripts/generate_config.py` |

Set one environment variable:

| Variable            | Value                                                    |
| ------------------- | -------------------------------------------------------- |
| `BEER_MANIFEST_URL` | `https://cdn.beer.example.com/manifest.json`             |

Then wire the site's own domain to Netlify:

- Add a **CNAME** record at your registrar: host `beer`, value your Netlify app name `<your-site-name>.netlify.app`.
- In Netlify → Site configuration → **Domain management**, add the subdomain `beer.example.com`, then **Verify DNS configuration** and let Netlify provision the HTTPS certificate (a few minutes).

This is separate from the `cdn.beer.example.com` record above — that one points at CloudFront for the photos; this one points the site itself at Netlify.

## DNS summary

| Subdomain              | Points to  | Purpose                          |
| ---------------------- | ---------- | -------------------------------- |
| `beer.example.com`     | Netlify    | Serves the website               |
| `cdn.beer.example.com` | CloudFront | Serves photos + manifest from S3 |

Once this is all done, you never come back here for normal use — just add photos and sync.
