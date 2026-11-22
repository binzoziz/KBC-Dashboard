# Deploy KBC Telegram bot to Cloud Run

## 1. Put the bot files in GitHub

Add/replace these files in the same GitHub folder:

- `telegram_bot.py`
- `kbc_processor.py`
- `menu.json`
- `Dockerfile`
- `requirements-bot.txt`
- `.dockerignore`

Do not upload `.env`, `service_account.json`, or any other credential file.

## 2. Create the service

In Google Cloud Console, open **Cloud Run → Connect repository** and connect the GitHub repository. Deploy the folder containing the `Dockerfile` as a web service. Suggested settings:

- Region: `us-central1`
- Minimum instances: `0`
- Maximum instances: `1`
- Container concurrency: `1`
- Request timeout: `300` seconds
- Allow unauthenticated invocations: enabled (Telegram must reach the endpoint; the bot checks the webhook secret)

The first deployment needs `WEBHOOK_URL` left empty. It creates the Cloud Run service URL without registering the webhook yet.

## 3. Add credentials and environment variables

In **Secret Manager**, create a secret containing the full contents of `service_account.json`. Reference that secret in the Cloud Run service as the environment variable `GOOGLE_SERVICE_ACCOUNT_JSON`. If prompted, grant the Cloud Run service identity permission to access the secret. The service account email in that JSON must have Editor access to the Google Sheet.

Set these environment variables in Cloud Run. Mark the token and webhook secret as secrets:

```text
BOT_MODE=webhook
TELEGRAM_BOT_TOKEN=<token dari BotFather>
ALLOWED_TELEGRAM_USER_IDS=<ID user Telegram, pisahkan dengan koma>
GOOGLE_SHEET_ID=<ID spreadsheet>
GOOGLE_SERVICE_ACCOUNT_JSON=<referensi secret dari Secret Manager>
TABLE_WORKSHEET=Billiard Master
FNB_WORKSHEET=F&B Master
WEBHOOK_PATH=telegram-webhook
WEBHOOK_SECRET=<string acak huruf/angka/underscore/hyphen>
WEBHOOK_URL=
```

Do not paste a real token or credential into GitHub.

## 4. Register the Telegram webhook

After the first deployment is ready, copy the service URL shown by Cloud Run. Stop the polling bot on the PC with `Ctrl+C`. Then set:

```text
WEBHOOK_URL=<Cloud Run service URL>/telegram-webhook
```

Save/deploy a new revision. On startup, the bot registers this URL with Telegram. Open the service URL in a browser; `/` should show `{"status":"ok","service":"kbc-telegram-importer"}`.

## 5. Send reports

Send `/start`, then send a PDF or ZIP in the bot's private chat. Include `/com1` or `/com2` as the file caption, or include `COM1` / `COM2` in the filename. The caption is recommended because Cloud Run may scale down and lose in-memory source selection.

The same parser and Google Sheets append logic are used. Existing `ID Unik` values continue to prevent duplicate rows when a file is resent.

## Billing note

Cloud Run requires an active billing account. Free-tier quotas apply to eligible usage; usage beyond the quotas or resources outside the free tier can be billed. A Free Trial account must be upgraded before it closes if the service should keep running.
