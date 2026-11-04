# ads-tools

Helpers for creating the PocketRook test ads in ChatGPT Ads. Run every command from inside this folder (`cd ads-tools`) unless noted.

**Everything in this repo is public on GitHub Pages. Never add anything private (keys, tokens, account IDs, customer data).**

## Files

| File | What it is |
|---|---|
| `pages.csv` | One row per ad. Columns: `group_name, context_hints, title, body, target_url, image_url`. `context_hints` are separated by `\|`. |
| `bulk_ads.py` | Builds one campaign, plus one ad group and one ad per CSV row, as a Bulk API job. Standard library only. |
| `check_urls.py` | Checks `pages.csv` before you upload: copy lengths, that the landing pages and images respond, and that each image is a square PNG between 640 and 1200 px. Standard library only. |
| `preview.json` | Not committed (it is in `.gitignore`). If you save the preview output, save it here. |

## Check the CSV first

```
python3 check_urls.py pages.csv                   # live: fetches the public URLs (works after the PR is merged and Pages has redeployed)
python3 check_urls.py --local-root .. pages.csv   # offline: checks the image files in this repo; skips the landing-page check
```

Each row prints PASS or FAIL with the reason. The exit code is 1 if anything failed.

## Upload commands, in this order

```
python3 bulk_ads.py pages.csv --campaign-name "PocketRook - November test" --budget 50 --billing click --countries US --tag pr-nov1
python3 bulk_ads.py pages.csv --campaign-name "PocketRook - November test" --budget 50 --billing click --countries US --tag pr-nov1 --validate-only    # needs OPENAI_ADS_API_KEY
python3 bulk_ads.py pages.csv --campaign-name "PocketRook - November test" --budget 50 --billing click --countries US --tag pr-nov1 --submit           # creates PAUSED resources
```

1. The first command only previews. It prints the JSON it would send and makes no network request.
2. `--validate-only` sends the job to OpenAI with `validate_only=true`. OpenAI checks fields and dependencies and changes nothing.
3. `--submit` creates the campaign, ad groups and ads for real.

Rules to remember:

- **The API key comes from the `OPENAI_ADS_API_KEY` environment variable only.** Set it in your shell for the session (for example `export OPENAI_ADS_API_KEY=...`). Never put it in a file, a command-line argument, a commit, a PR or an issue. `.env` and `*.key` are in `.gitignore` as a safety net, not as permission.
- **The Bulk API is a limited preview, enabled per ad account.** A 404 from it means your account is not enabled. The fix is to ask the OpenAI account team.
- **Everything is created paused.** Check it in Ads Manager, then activate it there. Nothing delivers until you do.
- **Use a new `--tag` for every new batch.** The tag is part of the idempotency keys, so re-running with the same tag and the same data is a safe retry, while a new batch needs a new tag.

Official docs: https://developers.openai.com/ads/bulk-api.md

## Pixel install

The conversion tracking in `index.html` (events `page_viewed` and `lead_created`) only does anything once the Pixel snippet is on the page. Until then the page logs `ad_event_skipped` in its on-page console and sends nothing.

1. In Ads Manager, open the **Conversions** tab and create a Pixel.
2. Copy the install snippet exactly as shown. Do not edit it.
3. Paste it into `index.html` inside `<head>`, between these two comments, and keep both comments:

   ```html
   <!-- ===== AD PIXEL / TAG PLACEHOLDER: paste your ChatGPT Ads pixel or tag snippet below this line. Keep it inside <head>. ===== -->
   <!-- ===== END AD PIXEL / TAG PLACEHOLDER ===== -->
   ```

   Alternatively, save the snippet unchanged as `_incoming/pixel-snippet.html` (a local folder that is never committed) and ask Claude Code to run the pixel wiring step again.
4. Commit, merge, wait about a minute for Pages to redeploy, then open the live page and confirm the on-page console shows `ad_event_sent` rows.

Docs: https://developers.openai.com/ads/measurement-pixel.md and https://developers.openai.com/ads/supported-events.md
