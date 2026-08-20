# Infrastructure — one-time setup

Terraform provisions a self-contained AWS stack for beer-site: a private S3 bucket, a CloudFront distribution to serve it, an ACM certificate, CloudFront Origin Access Control, and an IAM user the CLI uses to upload. Everyday photo management doesn't touch Terraform — see [`../scripts/README.md`](../scripts/README.md).

## What gets created

- **S3 bucket** — fully private (all public access blocked). Stores photos and `manifest.json`. Direct S3 URLs return 403.
- **CloudFront + OAC** — the only thing allowed to read the bucket, via SigV4 signing. Serves everything over `cdn.beer.example.com`. Photos cache for a year; `manifest.json` is served uncached so metadata edits appear immediately.
- **ACM certificate** — the TLS cert for the CDN subdomain, in `us-east-1` (a CloudFront requirement).
- **IAM uploader user** — scoped to put/get/delete/list on the bucket. Its keys go in `.env` for the CLI.

## Prerequisites

- Python 3.10+, [Terraform](https://developer.hashicorp.com/terraform/install), the [AWS CLI](https://aws.amazon.com/cli/), and an AWS + Netlify account.
- A recent AWS Terraform provider (`main.tf` pins `~> 6.0`) — required for the `ap-southeast-6` (New Zealand) region.
- `ap-southeast-6` is an opt-in region: enable it in the AWS console (Account → Regions, or the Regions and Zones page) before applying.

```bash
pip install -r ../requirements.txt
aws configure --profile your-aws-profile
```

## Steps

Commands assume a POSIX shell. In PowerShell, quote the Terraform `-target` value and use `python`/`copy` for `python3`/`cp`.

### 1. Configure variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

| Variable          | What to set                                                    |
| ----------------- | ------------------------------------------------------------- |
| `bucket_name`     | A globally-unique S3 bucket name                               |
| `aws_region`      | `ap-southeast-6` (Asia Pacific, New Zealand)                   |
| `aws_profile`     | Your AWS CLI profile                                           |
| `cdn_domain`      | The CDN subdomain, e.g. `cdn.beer.example.com`                 |
| `allowed_origins` | Your site origin, e.g. `["https://beer.example.com"]`          |

### 2. Create and validate the certificate

CloudFront needs a validated certificate before it can build, so create the cert on its own first:

```bash
terraform init
terraform apply -target="aws_acm_certificate.beer"
terraform output acm_certificate_validation_options
```

`acm_certificate_validation_options` prints a validation record — add it as a CNAME in your DNS provider:

| Field | Looks like                        | Goes in the registrar's… |
| ----- | --------------------------------- | ------------------------ |
| name  | `_a1b2c3….cdn.beer.example.com`   | Host / Name              |
| type  | `CNAME`                           | Record type              |
| value | `_x7y8z9….acm-validations.aws.`   | Value / Points to        |

Validation is automatic — ACM flips the certificate to **Issued** once the CNAME resolves. Check status in the ACM console in **us-east-1**, or with:

```bash
aws acm list-certificates --region us-east-1
aws acm describe-certificate --region us-east-1 --certificate-arn <arn> --query "Certificate.Status"
```

Leave the validation CNAME in place permanently — ACM reuses it to auto-renew the certificate.

### 3. Provision the rest

```bash
terraform apply
```

Creates the bucket, CloudFront distribution, bucket policy, OAC, and IAM uploader.

### 4. Point DNS at CloudFront

```bash
terraform output cloudfront_domain
```

Add a CNAME for `cdn.beer.example.com` → that CloudFront domain.

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

| Setting           | Value                                                                   |
| ----------------- | ---------------------------------------------------------------------- |
| Publish directory | `site`                                                                  |
| Build command     | `pip install -r requirements.txt && python scripts/generate_config.py` |

Set one environment variable:

| Variable            | Value                                        |
| ------------------- | -------------------------------------------- |
| `BEER_MANIFEST_URL` | `https://cdn.beer.example.com/manifest.json` |

Then wire the site's domain to Netlify:

- Add a CNAME at your DNS provider: host `beer`, value your Netlify app name `<your-site-name>.netlify.app`.
- In Netlify → Site configuration → Domain management, add `beer.example.com`, then Verify DNS configuration and let Netlify provision the HTTPS certificate (a few minutes).

## DNS summary

| Subdomain              | Points to  | Purpose                          |
| ---------------------- | ---------- | -------------------------------- |
| `beer.example.com`     | Netlify    | Serves the website               |
| `cdn.beer.example.com` | CloudFront | Serves photos + manifest from S3 |
