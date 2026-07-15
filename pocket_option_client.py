"""
Pocket Option automation via Playwright (SYNC API), driving a remote Chrome
browser hosted by Hyperbrowser (stealth mode), with the reCAPTCHA solved
for FREE via audio-challenge transcription (playwright-recaptcha library,
using Google's free speech recognition — no paid CAPTCHA service).

Requires HYPERBROWSER_API_KEY env var (from hyperbrowser.ai dashboard).
Requires ffmpeg installed in the container (see Dockerfile) for audio
transcription.

ARCHITECTURE NOTE: playwright-recaptcha only supports Playwright's sync
API, which is not thread-safe across arbitrary threads. So each Telegram
user's session gets its own single-worker background thread, and all
operations for that user are routed through that same thread via a
dedicated ThreadPoolExecutor. This keeps FastAPI's async event loop
non-blocking while still using the sync Playwright API safely.

IMPORTANT CAVEATS:
- Pocket Option has no official public API — this drives their actual
  web UI, which will break whenever they change their frontend, and it
  runs against their Terms of Service.
- Free audio-based CAPTCHA solving is less reliable than paid services —
  expect occasional failures; retrying the /connect call is reasonable.
- Selectors below are best-effort placeholders — VERIFY AND UPDATE them
  against the live site before relying on this for real trades.
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright
from hyperbrowser import Hyperbrowser
from hyperbrowser.models import CreateSessionParams
from playwright_recaptcha import recaptchav2

LOGIN_URL = "https://pocketoption.com/en/login/"

HYPERBROWSER_API_KEY = os.environ.get("HYPERBROWSER_API_KEY", "")
_hb = Hyperbrowser(api_key=HYPERBROWSER_API_KEY) if HYPERBROWSER_API_KEY else None

# One single-worker executor per telegram_user_id — guarantees all
# Playwright sync-API calls for that user always run on the same thread.
_executors: dict[str, ThreadPoolExecutor] = {}
_state: dict[str, dict] = {}  # holds playwright/browser/page per user


def _get_executor(telegram_user_id: str) -> ThreadPoolExecutor:
    if telegram_user_id not in _executors:
        _executors[telegram_user_id] = ThreadPoolExecutor(max_workers=1)
    return _executors[telegram_user_id]


def _sync_connect(telegram_user_id: str):
    if not _hb:
        raise RuntimeError("HYPERBROWSER_API_KEY not configured")

    session = _hb.sessions.create(params=CreateSessionParams(use_stealth=True))
    if getattr(session, "live_url", None):
        print(f"Hyperbrowser live debug URL: {session.live_url}")

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(session.ws_endpoint)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.pages[0] if context.pages else context.new_page()

    _state[telegram_user_id] = {
        "pw": pw, "browser": browser, "page": page, "session_id": session.id,
    }
    return page


def _sync_login(telegram_user_id: str, email: str, password: str, mode: str) -> dict:
    page = _state.get(telegram_user_id, {}).get("page") or _sync_connect(telegram_user_id)

    page.goto(LOGIN_URL, wait_until="commit", timeout=60000)
    page.wait_for_selector("input[name='email']", timeout=45000)
    page.fill("input[name='email']", email)
    page.fill("input[name='password']", password)

    # Solve the reCAPTCHA for free via audio-challenge transcription
    try:
        with recaptchav2.SyncSolver(page) as solver:
            solver.solve_recaptcha(wait=True)
    except Exception as e:
        print(f"reCAPTCHA solve attempt failed or none present: {e}")

    page.click("button[type='submit']")

    # Wait for the trading dashboard to load
    page.wait_for_selector("[class*='balance']", timeout=20000)

    # Switch account mode (demo/live) — selector is a placeholder, verify against live site
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

async def login(telegram_user_id: str, email: str, password: str, mode: str = "demo") -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(telegram_user_id), _sync_login, telegram_user_id, email, password, mode
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
