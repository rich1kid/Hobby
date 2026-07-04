# Jeff's Bot — Trading Execution Service

Standalone service (deploy on Railway) that reads encrypted credentials from
Supabase (populated by the Telegram bot) and executes real account
connections + trades for MT5 (via MetaApi) and Pocket Option (via Selenium).

## Why this is separate from Lovable

Lovable's backend runs on Supabase Edge Functions (serverless, short-lived).
This service needs:
- A persistent process (MetaApi SDK keeps a live connection)
- A real headless Chrome browser (Pocket Option has no API, so Selenium drives
  the actual website)

Neither works in a serverless edge function, hence Railway.

## Before you deploy — 3 things you MUST set up

1. **MetaApi account**: sign up at https://app.metaapi.cloud, generate an API
   token, put it in `METAAPI_TOKEN`. This is Anthropic-unrelated, third-party,
   and has its own free tier limits — check their pricing before connecting
   many accounts.

2. **Shared encryption key**: the Python `crypto_utils.py` here must decrypt
   with the *exact same key* your Supabase edge function used to encrypt.
   Go check the Lovable project's edge function code for how
   `password_encrypted` is generated, and get that same key value into
   `ENCRYPTION_KEY` here. If they don't match, decryption will fail with an
   auth-tag error — that's your signal the keys are out of sync.

3. **Supabase service role key**: from your Supabase project settings → API.
   This lets the service read the `mt5_accounts` / `pocket_option_accounts`
   tables directly (bypassing row-level security, so keep this key secret —
   never expose it to a frontend).

## Deploy to Railway

```
railway login
railway init
railway up
```

Then set the environment variables from `.env.example` in the Railway
dashboard (Variables tab). Railway will build from the included `Dockerfile`
automatically (needed for Chrome/Selenium support).

## Pocket Option — read this before relying on it

- No official API exists. This drives the real website via Selenium.
- Selectors in `pocket_option_client.py` are **placeholders** — Pocket
  Option's frontend will not match these exactly. Open Chrome devtools on
  the live site, inspect the login form, balance display, asset search, and
  Call/Put buttons, and update the `By.CSS_SELECTOR` values accordingly
  before trusting this with real trades.
- This operates against Pocket Option's Terms of Service. You accepted that
  risk already — just flagging it's still true here in the code.
- Demo/live switching depends on finding the account-type toggle — verify
  that selector too.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/mt5/account/{telegram_user_id}` | Connect + return balance/positions |
| POST | `/mt5/trade/{telegram_user_id}` | Place a market order |
| POST | `/pocket-option/connect/{telegram_user_id}?mode=demo\|live` | Login, switch mode |
| GET | `/pocket-option/balance/{telegram_user_id}` | Read current balance |
| POST | `/pocket-option/trade/{telegram_user_id}` | Place a call/put trade |
| POST | `/pocket-option/disconnect/{telegram_user_id}` | Close browser session |

## Wiring this back to the bot / dashboard

Once deployed, you'll have a Railway URL like
`https://jeffsbot-trading.up.railway.app`. Give me that URL and I'll update
the Telegram bot (in Lovable) to call these endpoints — e.g. so `/balance`
in Telegram actually hits `/mt5/account/{id}` here, and the admin dashboard
can show real "Connected" status instead of just "Stored".
