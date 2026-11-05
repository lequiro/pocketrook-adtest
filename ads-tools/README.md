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

**Status: installed.** The ChatGPT Ads pixel snippet is in the `<head>` of `index.html`, between these two comments (keep both):

```html
<!-- ===== AD PIXEL / TAG PLACEHOLDER: paste your ChatGPT Ads pixel or tag snippet below this line. Keep it inside <head>. ===== -->
<!-- ===== END AD PIXEL / TAG PLACEHOLDER ===== -->
```

The snippet's own JavaScript is wrapped in a guard, so visits from `localhost`, `127.0.0.1` and `[::1]` never load it. Local testing therefore can't send events to the ad account.

The page sends two events, only through `sendAdEvent()` in the inline script:

| Event | When | Data |
|---|---|---|
| `page_viewed` | Once on page load | `{ type: 'contents' }` |
| `lead_created` | Valid email submitted in the lead form | `{ type: 'customer_action' }` |

Each call carries a fresh UUID `event_id` (used to deduplicate against server events later). No email, level or other form value is ever sent. The form is simulated, so `lead_created` records a **test** conversion, not a real signup.

### Check that it works

1. Open the live page and expand the on-page "Ad test console".
2. `ad_event_sent` rows mean the call was handed to the pixel. `ad_event_skipped` means the pixel did not load (you are on localhost, or the snippet is missing).
3. Confirm in Ads Manager, on the **Conversions** tab, that the Pixel is receiving the events. A console row alone does not prove OpenAI received them.

### Things to know

- The snippet currently has `debug:true`, which makes the SDK log to visitors' browser consoles. Remove it once you have confirmed events arrive, if you want a quieter console.
- The Pixel ID in the page source is public by design. It is not a secret, but the repo is public, so never add API keys or tokens.

### Replace or reinstall the snippet

1. In Ads Manager, open the **Conversions** tab and create or open the Pixel.
2. Copy the install snippet exactly as shown. Do not edit it.
3. Replace everything between the two placeholder comments with it. If the snippet is a single `<script>` block, keep the localhost guard by wrapping only its inner JavaScript:

   ```html
   <script>
   if (!/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)) {
     /* snippet's JavaScript, unchanged */
   }
   </script>
   ```

   Alternatively, save the snippet unchanged as `_incoming/pixel-snippet.html` (a local folder that is never committed) and ask Claude Code to run the pixel wiring step again.
4. Commit, merge, wait about a minute for Pages to redeploy, then repeat the checks above.

Docs: https://developers.openai.com/ads/measurement-pixel.md and https://developers.openai.com/ads/supported-events.md
