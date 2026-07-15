"""
Fetches stored (still-encrypted) credentials via Lovable's internal-accounts
Edge Function, since the raw Supabase tables are locked behind RLS with only
service_role access — which Lovable Cloud doesn't expose to us directly.
"""
import os
import httpx

INTERNAL_ACCOUNTS_URL = os.environ.get(
    "INTERNAL_ACCOUNTS_URL",
    "https://thecsylxzkfknhfvjguo.supabase.co/functions/v1/internal-accounts",
)
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

HEADERS = {"X-Internal-Secret": INTERNAL_API_SECRET}


async def get_mt5_account(telegram_user_id: str) -> dict | None:
    params = {"telegram_user_id": telegram_user_id, "type": "mt5"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(INTERNAL_ACCOUNTS_URL, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def get_pocket_option_account(telegram_user_id: str) -> dict | None:
    params = {"telegram_user_id": telegram_user_id, "type": "pocket_option"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(INTERNAL_ACCOUNTS_URL, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def get_pocket_option_session(telegram_user_id: str) -> dict | None:
    """Returns {'storage_state': ..., 'mode': ..., 'updated_at': ...} or None if no saved session."""
    params = {"telegram_user_id": telegram_user_id, "type": "pocket_option_session"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(INTERNAL_ACCOUNTS_URL, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def save_pocket_option_session(telegram_user_id: str, storage_state: str, mode: str) -> None:
    body = {"telegram_user_id": telegram_user_id, "storage_state": storage_state, "mode": mode}
    params = {"type": "pocket_option_session"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(INTERNAL_ACCOUNTS_URL, headers=HEADERS, params=params, json=body, timeout=15)
        resp.raise_for_status()
