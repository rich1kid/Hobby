import os
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}


async def get_mt5_account(telegram_user_id: str) -> dict | None:
    url = f"{SUPABASE_URL}/rest/v1/mt5_accounts?telegram_user_id=eq.{telegram_user_id}&select=*"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


async def get_pocket_option_account(telegram_user_id: str) -> dict | None:
    url = f"{SUPABASE_URL}/rest/v1/pocket_option_accounts?telegram_user_id=eq.{telegram_user_id}&select=*"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None
