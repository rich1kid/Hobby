"""
Pocket Option automation via Playwright (SYNC API), driving a remote Chrome
browser hosted by Hyperbrowser (stealth mode).

STRATEGY: reCAPTCHA blocks fully-automated login (Google's own risk engine
flags datacenter-IP traffic before a challenge is even solvable — confirmed
via testing, not a selector/code issue). Since there's no budget for a
residential proxy, login happens MANUALLY once via a live browser view you
open yourself, then we save that session's cookies and reuse them for all
future automated actions — reCAPTCHA only guards the login step, not an
already-authenticated session.

Flow:
1. start_manual_login()  -> gives you a live_url to open and log in through
2. complete_manual_login() -> call after you've logged in; saves the session
3. login() -> for future calls, tries to reuse the saved session (no
   credentials/captcha needed) until it expires, at which point you repeat
   steps 1-2.

Requires HYPERBROWSER_API_KEY env var.

IMPORTANT CAVEATS:
- Pocket Option has no official public API — this drives their actual
  web UI, which will break whenever they change their frontend, and it
  runs against their Terms of Service.
- Saved sessions expire eventually (exact duration unknown — Pocket
  Option doesn't publish this) — expect to redo manual login periodically.
- Selectors below are best-effort placeholders — VERIFY AND UPDATE them
  against the live site before relying on this for real trades.
"""
import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright
from hyperbrowser import Hyperbrowser
from hyperbrowser.models import CreateSessionParams

import db

LOGIN_URL = "https://pocketoption.com/en/login/"

HYPERBROWSER_API_KEY = os.environ.get("HYPERBROWSER_API_KEY", "")
_hb = Hyperbrowser(api_key=HYPERBROWSER_API_KEY) if HYPERBROWSER_API_KEY else None

# One single-worker executor per telegram_user_id — guarantees all
# Playwright sync-API calls for that user always run on the same thread
# (sync Playwright is not safe to use across arbitrary threads).
_executors: dict[str, ThreadPoolExecutor] = {}
_state: dict[str, dict] = {}  # holds playwright/browser/page per user


def _get_executor(telegram_user_id: str) -> ThreadPoolExecutor:
    if telegram_user_id not in _executors:
        _executors[telegram_user_id] = ThreadPoolExecutor(max_workers=1)
    return _executors[telegram_user_id]


def _sync_connect(telegram_user_id: str, storage_state: str | None = None):
    if not _hb:
        raise RuntimeError("HYPERBROWSER_API_KEY not configured")

    session = _hb.sessions.create(params=CreateSessionParams(use_stealth=True))
    live_url = getattr(session, "live_url", None)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(session.ws_endpoint)

    if storage_state:
        context = browser.new_context(storage_state=json.loads(storage_state))
    else:
        context = browser.contexts[0] if browser.contexts else browser.new_context()

    page = context.pages[0] if context.pages else context.new_page()

    _state[telegram_user_id] = {
        "pw": pw, "browser": browser, "context": context, "page": page,
        "session_id": session.id, "live_url": live_url,
    }
    return _state[telegram_user_id]


def _sync_start_manual_login(telegram_user_id: str) -> str:
    state = _sync_connect(telegram_user_id)
    state["page"].goto(LOGIN_URL, wait_until="commit", timeout=60000)
    return state["live_url"]


def _sync_complete_manual_login(telegram_user_id: str) -> dict:
    state = _state.get(telegram_user_id)
    if not state:
        raise RuntimeError("No active manual-login session — call start_manual_login() first")
    page = state["page"]
    # Confirm we're actually logged in before saving
    page.wait_for_selector("[class*='balance']", timeout=15000)
    balance_text = page.locator("[class*='balance']").first.inner_text()
    storage_state = json.dumps(state["context"].storage_state())
    return {"storage_state": storage_state, "balance_raw_text": balance_text}


def _sync_use_saved_session(telegram_user_id: str, storage_state: str, mode: str) -> dict:
    state = _sync_connect(telegram_user_id, storage_state=storage_state)
    page = state["page"]
    page.goto(LOGIN_URL, wait_until="commit", timeout=60000)
    # If the saved session is still valid, Pocket Option should redirect
    # straight to the dashboard instead of showing the login form again.
    page.wait_for_selector("[class*='balance']", timeout=20000)

    try:
        account_switch = page.locator("[class*='account-switch']").first
        current_mode = account_switch.inner_text().strip().lower()
        if mode not in current_mode:
            account_switch.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    balance_text = page.locator("[class*='balance']").first.inner_text()
    return {"status": "logged_in", "mode": mode, "balance_raw_text": balance_text}


def _sync_get_balance(telegram_user_id: str) -> dict:
    page = _state.get(telegram_user_id, {}).get("page")
    if not page:
        raise RuntimeError("No active session — call login() first")
    balance_text = page.locator("[class*='balance']").first.inner_text()
    return {"balance_raw_text": balance_text}


def _sync_place_trade(telegram_user_id: str, asset: str, amount: float, direction: str, expiry_seconds: int) -> dict:
    page = _state.get(telegram_user_id, {}).get("page")
    if not page:
        raise RuntimeError("No active session — call login() first")

    asset_search = page.locator("[class*='asset-search']").first
    asset_search.fill(asset)
    page.wait_for_timeout(1000)
    page.locator("[class*='asset-item']").first.click()

    page.locator("[class*='amount-input']").first.fill(str(amount))
    page.locator("[class*='expiry-input']").first.fill(str(expiry_seconds))

    button_selector = "[class*='btn-call']" if direction == "call" else "[class*='btn-put']"
    page.locator(button_selector).first.click()

    return {"status": "trade_submitted", "asset": asset, "amount": amount, "direction": direction}


def _sync_close_session(telegram_user_id: str):
    state = _state.pop(telegram_user_id, None)
    if state:
        try:
            state["browser"].close()
        except Exception:
            pass
        try:
            state["pw"].stop()
        except Exception:
            pass
        if _hb and state.get("session_id"):
            try:
                _hb.sessions.stop(state["session_id"])
            except Exception:
                pass
    executor = _executors.pop(telegram_user_id, None)
    if executor:
        executor.shutdown(wait=False)


# ---------- Async wrappers used by main.py ----------

async def start_manual_login(telegram_user_id: str) -> dict:
    loop = asyncio.get_running_loop()
    live_url = await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_start_manual_login, telegram_user_id
    )
    return {"live_url": live_url, "instructions": "Open this URL, log in manually (solve any CAPTCHA), then call the complete endpoint."}


async def complete_manual_login(telegram_user_id: str, mode: str = "demo") -> dict:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_complete_manual_login, telegram_user_id
    )
    await db.save_pocket_option_session(telegram_user_id, result["storage_state"], mode)
    return {"status": "session_saved", "balance_raw_text": result["balance_raw_text"]}


async def login(telegram_user_id: str, mode: str = "demo") -> dict:
    session = await db.get_pocket_option_session(telegram_user_id)
    if not session:
        raise RuntimeError(
            "No saved session for this user. Call /pocket-option/manual-login/start first, "
            "log in manually, then /pocket-option/manual-login/complete."
        )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_use_saved_session,
        telegram_user_id, session["storage_state"], mode,
    )


async def get_balance(telegram_user_id: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_get_balance, telegram_user_id
    )


async def place_trade(telegram_user_id: str, asset: str, amount: float, direction: str, expiry_seconds: int) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_place_trade,
        telegram_user_id, asset, amount, direction, expiry_seconds,
    )


async def close_session(telegram_user_id: str):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_get_executor(telegram_user_id), _sync_close_session, telegram_user_id)
