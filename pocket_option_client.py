"""
Pocket Option automation via Playwright, driving a REMOTE Chrome browser
hosted by Hyperbrowser — chosen specifically because it bundles stealth
mode + proxy routing to help get past anti-bot detection, which Steel's
free tier didn't offer and which we hit as a real wall (Pocket Option's
login page rendered completely blank for our previous automated sessions).

Requires HYPERBROWSER_API_KEY env var (from hyperbrowser.ai dashboard).
Free tier: 1,000 starter credits, 1 concurrent browser.

IMPORTANT CAVEATS:
- Pocket Option has no official public API — this drives their actual
  web UI, which will break whenever they change their frontend, and it
  runs against their Terms of Service.
- Even with stealth+proxy, there's no guarantee this gets past whatever
  Pocket Option runs. If the page still renders blank, that's a strong
  signal their detection is more sophisticated than standard stealth
  mode can handle.
- Selectors below are best-effort placeholders — VERIFY AND UPDATE them
  against the live site before relying on this for real trades.
"""
import os
from playwright.async_api import async_playwright, Browser, Page
from hyperbrowser import AsyncHyperbrowser
from hyperbrowser.models import CreateSessionParams

LOGIN_URL = "https://pocketoption.com/en/login/"

HYPERBROWSER_API_KEY = os.environ.get("HYPERBROWSER_API_KEY", "")
_hb = AsyncHyperbrowser(api_key=HYPERBROWSER_API_KEY) if HYPERBROWSER_API_KEY else None

# Per-user active Playwright/browser/page + Hyperbrowser session, so we
# can clean up properly. In-memory — fine for a single-instance deployment.
_playwright_instances: dict[str, object] = {}
_browsers: dict[str, Browser] = {}
_pages: dict[str, Page] = {}
_hb_session_ids: dict[str, str] = {}


async def _get_or_create_page(telegram_user_id: str) -> Page:
    if telegram_user_id in _pages:
        return _pages[telegram_user_id]

    if not _hb:
        raise RuntimeError("HYPERBROWSER_API_KEY not configured")

    session = await _hb.sessions.create(
        params=CreateSessionParams(use_stealth=True, use_proxy=True)
    )
    _hb_session_ids[telegram_user_id] = session.id
    if getattr(session, "live_url", None):
        print(f"Hyperbrowser live debug URL: {session.live_url}")

    pw = await async_playwright().start()
    _playwright_instances[telegram_user_id] = pw

    browser = await pw.chromium.connect_over_cdp(session.ws_endpoint)
    _browsers[telegram_user_id] = browser

    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    _pages[telegram_user_id] = page
    return page


async def login(telegram_user_id: str, email: str, password: str, mode: str = "demo") -> dict:
    """Logs in and switches to demo or live account. Returns current balance."""
    page = await _get_or_create_page(telegram_user_id)

    await page.goto(LOGIN_URL, wait_until="commit", timeout=60000)
    await page.wait_for_selector("input[name='email']", timeout=45000)
    await page.fill("input[name='email']", email)
    await page.fill("input[name='password']", password)
    await page.click("button[type='submit']")

    # Wait for the trading dashboard to load
    await page.wait_for_selector("[class*='balance']", timeout=20000)

    # Switch account mode (demo/live) — selector is a placeholder, verify against live site
    try:
        account_switch = page.locator("[class*='account-switch']").first
        current_mode = (await account_switch.inner_text()).strip().lower()
        if mode not in current_mode:
            await account_switch.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass  # If the switch isn't found, proceed with whatever account is default

    balance_text = await page.locator("[class*='balance']").first.inner_text()
    return {"status": "logged_in", "mode": mode, "balance_raw_text": balance_text}


async def get_balance(telegram_user_id: str) -> dict:
    if telegram_user_id not in _pages:
        raise RuntimeError("No active session — call login() first")
    page = _pages[telegram_user_id]
    balance_text = await page.locator("[class*='balance']").first.inner_text()
    return {"balance_raw_text": balance_text}


async def place_trade(telegram_user_id: str, asset: str, amount: float, direction: str, expiry_seconds: int) -> dict:
    """direction: 'call' (up) or 'put' (down). Selectors are placeholders — verify against live site."""
    if telegram_user_id not in _pages:
        raise RuntimeError("No active session — call login() first")
    page = _pages[telegram_user_id]

    asset_search = page.locator("[class*='asset-search']").first
    await asset_search.fill(asset)
    await page.wait_for_timeout(1000)
    await page.locator("[class*='asset-item']").first.click()

    amount_field = page.locator("[class*='amount-input']").first
    await amount_field.fill(str(amount))

    expiry_field = page.locator("[class*='expiry-input']").first
    await expiry_field.fill(str(expiry_seconds))

    button_selector = "[class*='btn-call']" if direction == "call" else "[class*='btn-put']"
    await page.locator(button_selector).first.click()

    return {"status": "trade_submitted", "asset": asset, "amount": amount, "direction": direction}


async def close_session(telegram_user_id: str):
    browser = _browsers.pop(telegram_user_id, None)
    if browser:
        await browser.close()
    pw = _playwright_instances.pop(telegram_user_id, None)
    if pw:
        await pw.stop()
    _pages.pop(telegram_user_id, None)
    session_id = _hb_session_ids.pop(telegram_user_id, None)
    if session_id and _hb:
        try:
            await _hb.sessions.stop(session_id)
        except Exception:
            pass
