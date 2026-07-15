#!/usr/bin/env python3
"""
generate_config.py — Netlify build step

Writes site/config.js so the browser knows where to fetch the manifest.
The beer site is open (no password gate), so the only thing baked in is the
manifest URL.

Required Netlify environment variable:
    BEER_MANIFEST_URL   full URL to manifest.json (e.g. https://cdn.beer.example.com/manifest.json)
"""

import json
import os
import sys
from pathlib import Path

manifest_url = os.environ.get("BEER_MANIFEST_URL", "")

if not manifest_url:
    print("⚠️  BEER_MANIFEST_URL is not set — site will not load beers.", file=sys.stderr)

config = {"manifestUrl": manifest_url}

output = (
    "// Auto-generated at build time — do not edit or commit\n"
    f"window.BEER_SITE_CONFIG = {json.dumps(config, indent=2)};\n"
)

Path("./site/config.js").write_text(output)

print("✅  config.js generated")
if manifest_url:
    print(f"   📦 Manifest URL: {manifest_url}")
