"""
MT5 connection via a RapidAPI-hosted MT5 bridge (e.g. "Forex Brokers and
Servers - MetaTrader" / similar listings like Metasync).

⚠️ TRUST WARNING — read before using with any real credentials:
This class of RapidAPI MT5 bridge is a third-party service that receives your
raw MT5 login + password on its own servers, run by an unverified individual
developer. Public discussion (Forex Factory) around at least one very similar
listing raised real concerns — thin/missing docs, no verifiable legal or
support presence, "vibe-coded" implementation. There is no way for this code
to confirm what that third party does with credentials once received.

Because of that, this module HARD-BLOCKS anything that doesn't look like a
demo account. There is no override flag. If you later verify this provider is
trustworthy (real company, audited, verifiable docs) and want to lift this for
live accounts, do that deliberately in this file — don't work around it.

Docs for the exact endpoint schema were not available to verify at the time
this was written. Check your RapidAPI dashboard's "Endpoints" tab for the
exact path/param names for your specific listing and adjust accordingly.
"""
import os
import httpx

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.environ.get("RAPIDAPI_HOST", "forex-brokers-and-servers-metatrader.p.rapidapi.com")
BASE_URL = f"https://{RAPIDAPI_HOST}"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json",
}


class LiveAccountBlockedError(Exception):
    """Raised when a request targets what looks like a live (non-demo) account."""


def _assert_demo(server: str):
    if "demo" not in server.lower():
        raise LiveAccountBlockedError(
            f"Refusing to connect: server name '{server}' does not look like a demo "
            "server. This RapidAPI bridge is restricted to demo accounts only until "
            "the provider's trustworthiness is independently verified."
        )


async def connect(login: str, password: str, server: str) -> dict:
    _assert_demo(server)
    payload = {"login": login, "password": password, "server": server}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/connect", json=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()


async def get_account_info(login: str, password: str, server: str) -> dict:
    _assert_demo(server)
    payload = {"login": login, "password": password, "server": server}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/account-info", json=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()


async def get_positions(login: str, password: str, server: str) -> dict:
    _assert_demo(server)
    payload = {"login": login, "password": password, "server": server}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/positions", json=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()


# NOTE: trade placement intentionally NOT implemented here yet.
# Once you've confirmed this provider's real endpoint schema and are
# comfortable with the trust model, add a place_trade() function following
# the same _assert_demo() guard pattern used above.
