"""
Pocket Option automation via Selenium (headless Chrome).

IMPORTANT CAVEATS:
- Pocket Option has no official public API. This drives their actual web UI,
  which means it WILL break whenever they change their frontend, and it runs
  against their Terms of Service. Expect to maintain these selectors.
- Requires a headless-Chrome-capable environment (Railway with a Chrome
  buildpack, or a Docker image with chromium installed — see Dockerfile).
- Demo vs Live is toggled via the account-type switch in the top nav after login.

Selectors below are best-effort placeholders based on Pocket Option's typical
layout as of early 2026 — VERIFY AND UPDATE them against the live site before
relying on this for real trades. Use browser devtools to confirm current
element IDs/classes.
"""
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

LOGIN_URL = "https://pocketoption.com/en/login/"

# Per-user active driver sessions (in-memory; fine for a single-instance
# Railway deployment, not for multi-instance scaling)
_sessions: dict[str, webdriver.Chrome] = {}


def _new_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")
    options.add_argument("--single-process")
    options.add_argument("--window-size=1024,768")
    return webdriver.Chrome(options=options)


def login(telegram_user_id: str, email: str, password: str, mode: str = "demo") -> dict:
    """Logs in and switches to demo or live account. Returns current balance."""
    driver = _sessions.get(telegram_user_id) or _new_driver()
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
