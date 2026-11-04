#!/usr/bin/env python3
"""Check pages.csv before a bulk upload. Standard library only.

Live mode (default): fetches target_url and image_url and expects HTTP 200;
the image must be a square PNG between 640 and 1200 px.
--local-root PATH: no network. Maps the public site URL to PATH and checks the
local image files instead. The target URL check is skipped.

Every row is also checked for: title 3-50 chars, body <= 100 chars,
target_url <= 2048 chars. Prints one PASS/FAIL line per row; exit 1 on any FAIL.
"""
import argparse
import csv
import os
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://lequiro.github.io/pocketrook-adtest/"
MIN_PX, MAX_PX = 640, 1200
PNG_SIG = b"\x89PNG\r\n\x1a\n"
UA = {"User-Agent": "pocketrook-check-urls/1.0"}


def png_size(head):
    """Return (width, height) from the first 24 bytes of a PNG, else raise ValueError."""
    if len(head) < 24 or head[:8] != PNG_SIG:
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def check_dims(w, h):
    if w != h:
        return f"image is {w}x{h}, must be square"
    if not MIN_PX <= w <= MAX_PX:
        return f"image is {w}x{h}, must be {MIN_PX}-{MAX_PX} px"
    return None


def fetch(url, nbytes=0):
    """GET url; return (status, content_type, first nbytes bytes). HTTP errors return their status."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(nbytes)
    except urllib.error.HTTPError as e:
        return e.code, "", b""


def check_text(row):
    errs = []
    if not 3 <= len(row["title"]) <= 50:
        errs.append(f"title is {len(row['title'])} chars, need 3-50")
    if len(row["body"]) > 100:
        errs.append(f"body is {len(row['body'])} chars, max 100")
    if len(row["target_url"]) > 2048:
        errs.append(f"target_url is {len(row['target_url'])} chars, max 2048")
    return errs


def check_local(row, root):
    url = row["image_url"]
    if not url.startswith(SITE):
        return [f"image_url is not under {SITE}"]
    rel = urllib.parse.unquote(urllib.parse.urlsplit(url[len(SITE):]).path)
    path = os.path.realpath(os.path.join(root, rel))
    if not path.startswith(os.path.realpath(root) + os.sep):
        return ["image_url points outside the local root"]
    if not os.path.isfile(path):
        return [f"missing local file {rel}"]
    try:
        with open(path, "rb") as f:
            err = check_dims(*png_size(f.read(24)))
    except ValueError as e:
        err = f"{rel}: {e}"
    return [err] if err else []


def check_live(row):
    errs = []
    status, _, _ = fetch(row["target_url"])
    if status != 200:
        errs.append(f"target_url returned HTTP {status}")
    status, ctype, head = fetch(row["image_url"], 24)
    if status != 200:
        errs.append(f"image_url returned HTTP {status}")
    elif not ctype.startswith("image/"):
        errs.append(f"image Content-Type is '{ctype}', need image/*")
    else:
        try:
            err = check_dims(*png_size(head))
        except ValueError as e:
            err = f"image: {e}"
        if err:
            errs.append(err)
    return errs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv_file")
    p.add_argument("--local-root", metavar="PATH", help="check local files instead of fetching URLs")
    a = p.parse_args()

    with open(a.csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    failed = False
    for i, row in enumerate(rows, 1):
        errs = check_text(row) + (check_local(row, a.local_root) if a.local_root else check_live(row))
        failed |= bool(errs)
        print(f"{'FAIL' if errs else 'PASS'} row {i} ({row['group_name']}): " + ("; ".join(errs) or "ok"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
