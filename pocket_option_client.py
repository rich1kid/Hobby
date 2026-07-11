"""
Pocket Option automation via Selenium, driving a REMOTE Chrome browser
hosted by Steel (steel.dev) instead of launching Chrome locally.

Why remote: Render's free tier only has 512MB RAM, which isn't reliably
enough for local headless Chrome on a real JS-heavy site like Pocket
Option's dashboard (it was crashing with OOM-style errors). Steel runs
the actual browser on their infrastructure — our service just sends it
commands over the network, so our own container's memory footprint
stays tiny.

Requires STEEL_API_KEY env var (from steel.dev dashboard).
Free tier: 100 browser-hours/month — plenty for testing and light use.

IMPORTANT CAVEATS (unchanged from before):
- Pocket Option has no official public API — this drives their actual
  web UI, which will break whenever they change their frontend, and it
  runs against their Terms of Service.
- Selectors below are best-effort placeholders — VERIFY AND UPDATE them
  against the live site before relying on this for real trades.
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from steel import Steel

LOGIN_URL = "https://pocketoption.com/en/login/"

STEEL_API_KEY = os.environ.get("STEEL_API_KEY", "")
_steel = Steel(steel_api_key=STEEL_API_KEY) if STEEL_API_KEY else None

# Per-user active driver sessions + their Steel session IDs (in-memory;
# fine for a single-instance deployment, not for multi-instance scaling)
_sessions: dict[str, webdriver.Remote] = {}
_steel_session_ids: dict[str, str] = {}


class SteelRemoteConnection(RemoteConnection):
    def __init__(self, remote_server_addr: str, session_id: str):
        super().__init__(remote_server_addr)
        self._session_id = session_id

    def get_remote_connection_headers(self, parsed_url, keep_alive=False):
        headers = super().get_remote_connection_headers(parsed_url, keep_alive)
        headers.update({
            "steel-api-key": STEEL_API_KEY,
            "session-id": self._session_id,
        })
        return headers


def _new_driver(telegram_user_id: str) -> webdriver.Remote:
    if not _steel:
        raise RuntimeError("STEEL_API_KEY not configured")
    session = _steel.sessions.create(is_selenium=True)
    _steel_session_ids[telegram_user_id] = session.id
    print(f"Steel live debug URL: {session.session_viewer_url}")
    driver = webdriver.Remote(
        command_executor=SteelRemoteConnection(
            remote_server_addr="http://connect.steelbrowser.com/selenium",
            session_id=session.id,
        ),
        options=webdriver.ChromeOptions(),
    )
    return driver


def login(telegram_user_id: str, email: str, password: str, mode: str = "demo") -> dict:
    """Logs in and switches to demo or live account. Returns current balance."""
    driver = _sessions.get(telegram_user_id) or _new_driver(telegram_user_id)
    _sessions[telegram_user_id] = driver

    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    password_field = driver.find_element(By.NAME, "password")
    email_field.send_keys(email)
    password_field.send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Wait for the trading dashboard to load
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='balance']")))

    # Switch account mode (demo/live) — selector is a placeholder, verify against live site
    try:
        account_switch = driver.find_element(By.CSS_SELECTOR, "[class*='account-switch']")
        current_mode = account_switch.text.strip().lower()
        if mode not in current_mode:
            account_switch.click()
            time.sleep(1)
    except Exception:
        pass  # If the switch isn't found, proceed with whatever account is default

    balance_el = driver.find_element(By.CSS_SELECTOR, "[class*='balance']")
    return {"status": "logged_in", "mode": mode, "balance_raw_text": balance_el.text}


def get_balance(telegram_user_id: str) -> dict:
    driver = _sessions.get(telegram_user_id)
    if not driver:
        raise RuntimeError("No active session — call login() first")
    balance_el = driver.find_element(By.CSS_SELECTOR, "[class*='balance']")
    return {"balance_raw_text": balance_el.text}


def place_trade(telegram_user_id: str, asset: str, amount: float, direction: str, expiry_seconds: int) -> dict:
    """direction: 'call' (up) or 'put' (down). Selectors are placeholders — verify against live site."""
    driver = _sessions.get(telegram_user_id)
    if not driver:
        raise RuntimeError("No active session — call login() first")

    wait = WebDriverWait(driver, 10)

    asset_search = driver.find_element(By.CSS_SELECTOR, "[class*='asset-search']")
    asset_search.clear()
    asset_search.send_keys(asset)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, "[class*='asset-item']").click()

    amount_field = driver.find_element(By.CSS_SELECTOR, "[class*='amount-input']")
    amount_field.clear()
    amount_field.send_keys(str(amount))

    expiry_field = driver.find_element(By.CSS_SELECTOR, "[class*='expiry-input']")
    expiry_field.clear()
    expiry_field.send_keys(str(expiry_seconds))

    button_selector = "[class*='btn-call']" if direction == "call" else "[class*='btn-put']"
    driver.find_element(By.CSS_SELECTOR, button_selector).click()

    return {"status": "trade_submitted", "asset": asset, "amount": amount, "direction": direction}


def close_session(telegram_user_id: str):
    driver = _sessions.pop(telegram_user_id, None)
    if driver:
        driver.quit()
    session_id = _steel_session_ids.pop(telegram_user_id, None)
    if session_id and _steel:
        try:
            _steel.sessions.release(session_id)
        except Exception:
            pass
