#!/usr/bin/env python3
"""Build and (optionally) submit a ChatGPT Ads Bulk API job from a small CSV.

One campaign, then one ad group + one ad per CSV row. Everything is created
PAUSED, so nothing starts delivering until you activate it yourself.

Modes (pick one):
  (default)         Build the JSON, check it locally, print it. No network.
  --validate-only   Send it with validate_only=true (OpenAI checks fields and
                    dependencies, changes nothing). Needs OPENAI_ADS_API_KEY.
  --submit          Send it for real and poll until the job finishes.

The API key is read from the OPENAI_ADS_API_KEY environment variable, never
from a file or a command-line argument.

The Bulk API is a limited preview. A 404 means the ad account is not enabled.
Docs: https://developers.openai.com/ads/bulk-api.md
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.ads.openai.com/v1"

# Limits copied from the official Bulk API page.
MAX_OPS = 1000
MIN_BUDGET_MICROS = 1_000_000
NAME_RANGE = (3, 1000)
TITLE_RANGE = (3, 50)
BODY_MAX = 100
URL_MAX = 2048
HINTS_MAX = 2000
KEY_MAX = 255


def slug(text):
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


def build_operations(rows, campaign_name, budget_micros, billing, countries, tag):
    """tag makes idempotency keys unique per run, e.g. 'nov-launch'."""
    camp_key = f"campaign-{tag}"
    ops = [{
        "operation_id": "create-campaign",
        "type": "campaign.create",
        "idempotency_key": camp_key,
        "input": {
            "name": campaign_name,
            "max_budget_micros": budget_micros,
            "billing_event_type": billing,      # "impression" or "click"
            "budget_type": "lifetime",
            "status": "paused",
            "target_countries": countries,
        },
    }]
    for i, r in enumerate(rows, 1):
        grp_key = f"adgroup-{tag}-{i}"
        ad_key = f"ad-{tag}-{i}"
        hints = [h.strip() for h in r["context_hints"].split("|") if h.strip()]
        ops.append({
            "operation_id": f"create-ad-group-{i}",
            "type": "ad_group.create",
            "idempotency_key": grp_key,
            "input": {
                "campaign_idempotency_key": camp_key,
                "name": r["group_name"],
                "context_hints": hints,
                "status": "paused",
            },
        })
        ops.append({
            "operation_id": f"create-ad-{i}",
            "type": "ad.create",
            "idempotency_key": ad_key,
            "input": {
                "campaign_idempotency_key": camp_key,
                "ad_group_idempotency_key": grp_key,
                "title": r["title"],
                "body": r["body"],
                "target_url": r["target_url"],
                "source_image_url": r["image_url"],
                "status": "paused",
            },
        })
    return ops


def check(ops):
    """Local checks against the documented limits. Returns a list of problems."""
    errs = []
    if not 1 <= len(ops) <= MAX_OPS:
        errs.append(f"{len(ops)} operations; must be 1..{MAX_OPS}")
    seen_ids, seen_keys = set(), set()
    for op in ops:
        oid, inp = op["operation_id"], op["input"]
        if oid in seen_ids:
            errs.append(f"duplicate operation_id {oid}")
        seen_ids.add(oid)
        key = op.get("idempotency_key")
        if key:
            if key in seen_keys:
                errs.append(f"duplicate idempotency_key {key}")
            seen_keys.add(key)
            if len(key) > KEY_MAX:
                errs.append(f"{oid}: idempotency_key too long")
        t = op["type"]
        if "name" in inp and not NAME_RANGE[0] <= len(inp["name"]) <= NAME_RANGE[1]:
            errs.append(f"{oid}: name must be {NAME_RANGE[0]}-{NAME_RANGE[1]} chars")
        if t == "campaign.create" and inp["max_budget_micros"] < MIN_BUDGET_MICROS:
            errs.append(f"{oid}: budget below {MIN_BUDGET_MICROS} micros")
        if t == "ad_group.create" and len(inp.get("context_hints", [])) > HINTS_MAX:
            errs.append(f"{oid}: more than {HINTS_MAX} context hints")
        if t == "ad.create":
            if not TITLE_RANGE[0] <= len(inp["title"]) <= TITLE_RANGE[1]:
                errs.append(f"{oid}: title is {len(inp['title'])} chars; need {TITLE_RANGE[0]}-{TITLE_RANGE[1]}")
            if len(inp["body"]) > BODY_MAX:
                errs.append(f"{oid}: body is {len(inp['body'])} chars; max {BODY_MAX}")
            for f in ("target_url", "source_image_url"):
                if not inp[f].startswith(("http://", "https://")) or len(inp[f]) > URL_MAX:
                    errs.append(f"{oid}: {f} must be http(s) and <= {URL_MAX} chars")
    return errs


def call(method, path, key, body=None, idem=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 404 and "bulk_mutation_jobs" in path:
            print("404 from the Bulk API: this ad account probably is not enabled "
                  "for the limited preview. Ask your OpenAI account team.", file=sys.stderr)
        print(f"HTTP {e.code}: {detail}", file=sys.stderr)
        sys.exit(1)


def run_job(ops, key, validate_only, job_key):
    body = {"validate_only": validate_only, "partial_failure": True, "operations": ops}
    status, job = call("POST", "/bulk_mutation_jobs", key, body, idem=job_key)
    print(f"Submitted ({status}): job {job['id']} status={job['status']}")
    job_id = job["id"]
    delay = 2
    while job["status"] in ("pending", "in_progress"):
        time.sleep(delay)
        delay = min(delay * 2, 30)
        _, job = call("GET", f"/bulk_mutation_jobs/{job_id}", key)
        print(f"  status={job['status']}")
    # Read every page of per-operation results.
    after, results = None, []
    while True:
        path = f"/bulk_mutation_jobs/{job_id}/operations?limit=100"
        if after:
            path += f"&after={after}"
        _, page = call("GET", path, key)
        results += page["data"]
        if not page.get("has_more"):
            break
        after = page["data"][-1]["operation_id"]
    print(f"\nJob finished: {job['status']}")
    for r in results:
        line = f"  {r['operation_id']:<22} {r['status']:<10} {r.get('resource_id') or ''}"
        if r["status"] == "failed":
            line += f"  error={r.get('error_code')}: {r.get('error')} retryable={r.get('retryable')} wait={r.get('retry_after_seconds')}"
        print(line)
    return job["status"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv_file")
    p.add_argument("--campaign-name", required=True)
    p.add_argument("--budget", type=float, required=True, help="lifetime budget in account currency, e.g. 100")
    p.add_argument("--billing", choices=["impression", "click"], default="click")
    p.add_argument("--countries", default="US", help="comma-separated ISO codes, e.g. US,CA")
    p.add_argument("--tag", required=True, help="unique label for this run, used in idempotency keys (e.g. nov-launch)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--submit", action="store_true")
    a = p.parse_args()

    with open(a.csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ops = build_operations(rows, a.campaign_name, int(round(a.budget * 1_000_000)),
                           a.billing, [c.strip().upper() for c in a.countries.split(",")], slug(a.tag))
    errs = check(ops)
    if errs:
        print("Fix these first:\n  " + "\n  ".join(errs), file=sys.stderr)
        sys.exit(2)

    if not (a.validate_only or a.submit):
        print(json.dumps({"validate_only": False, "partial_failure": True, "operations": ops}, indent=2))
        print(f"\nOK locally: {len(ops)} operations, nothing sent. "
              "Next: --validate-only, then --submit.", file=sys.stderr)
        return

    key = os.environ.get("OPENAI_ADS_API_KEY")
    if not key:
        sys.exit("Set OPENAI_ADS_API_KEY first (Ads Manager > Settings).")
    # Job-level key: reusing it with the same body is a safe retry; a new run needs a new tag.
    mode_name = "validate" if a.validate_only else "submit"
    run_job(ops, key, a.validate_only, f"{slug(a.tag)}-{mode_name}-job")


if __name__ == "__main__":
    main()
