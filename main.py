from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import db
import crypto_utils
import mt5_client
import mt5_client_rapidapi
import pocket_option_client

app = FastAPI(title="Jeff's Bot Trading Execution Service")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- MT5 ----------

@app.get("/mt5/account/{telegram_user_id}")
async def mt5_account_info(telegram_user_id: str):
    record = await db.get_mt5_account(telegram_user_id)
    if not record:
        raise HTTPException(404, "No MT5 account linked for this user")

    broker = record["broker"]
    login = record["login_number"]
    password = crypto_utils.decrypt_value(record["password_encrypted"])

    try:
        result = await mt5_client.get_account_info(telegram_user_id, broker, login, password)
        return result
    except Exception as e:
        raise HTTPException(502, f"MT5 connection failed: {e}")


class MT5TradeRequest(BaseModel):
    symbol: str
    volume: float
    order_type: str  # "ORDER_TYPE_BUY" | "ORDER_TYPE_SELL"
    stop_loss: float | None = None
    take_profit: float | None = None


@app.post("/mt5/trade/{telegram_user_id}")
async def mt5_place_trade(telegram_user_id: str, req: MT5TradeRequest):
    record = await db.get_mt5_account(telegram_user_id)
    if not record:
        raise HTTPException(404, "No MT5 account linked for this user")

    broker = record["broker"]
    login = record["login_number"]
    password = crypto_utils.decrypt_value(record["password_encrypted"])

    try:
        result = await mt5_client.place_trade(
            telegram_user_id, broker, login, password,
            req.symbol, req.volume, req.order_type, req.stop_loss, req.take_profit,
        )
        return result
    except Exception as e:
        raise HTTPException(502, f"MT5 trade failed: {e}")


# ---------- MT5 via RapidAPI (DEMO ACCOUNTS ONLY — see mt5_client_rapidapi.py) ----------

@app.get("/mt5-rapidapi/account/{telegram_user_id}")
async def mt5_rapidapi_account_info(telegram_user_id: str):
    record = await db.get_mt5_account(telegram_user_id)
    if not record:
        raise HTTPException(404, "No MT5 account linked for this user")

    broker = record["broker"]
    login = record["login_number"]
    password = crypto_utils.decrypt_value(record["password_encrypted"])

    try:
        info = await mt5_client_rapidapi.get_account_info(login, password, broker)
        positions = await mt5_client_rapidapi.get_positions(login, password, broker)
        return {"account_info": info, "positions": positions}
    except mt5_client_rapidapi.LiveAccountBlockedError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(502, f"RapidAPI MT5 connection failed: {e}")


# ---------- Pocket Option ----------

@app.post("/pocket-option/connect/{telegram_user_id}")
async def pocket_option_connect(telegram_user_id: str, mode: str = "demo"):
    if mode not in ("demo", "live"):
        raise HTTPException(400, "mode must be 'demo' or 'live'")

    record = await db.get_pocket_option_account(telegram_user_id)
    if not record:
        raise HTTPException(404, "No Pocket Option account linked for this user")

    email = record["email"]
    password = crypto_utils.decrypt_value(record["password_encrypted"])

    try:
        result = await pocket_option_client.login(telegram_user_id, email, password, mode)
        return result
    except Exception as e:
        raise HTTPException(502, f"Pocket Option login failed: {e}")


@app.get("/pocket-option/balance/{telegram_user_id}")
async def pocket_option_balance(telegram_user_id: str):
    try:
        return await pocket_option_client.get_balance(telegram_user_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


class PocketOptionTradeRequest(BaseModel):
    asset: str
    amount: float
    direction: str  # "call" | "put"
    expiry_seconds: int = 60


@app.post("/pocket-option/trade/{telegram_user_id}")
async def pocket_option_trade(telegram_user_id: str, req: PocketOptionTradeRequest):
    if req.direction not in ("call", "put"):
        raise HTTPException(400, "direction must be 'call' or 'put'")
    try:
        result = await pocket_option_client.place_trade(
            telegram_user_id, req.asset, req.amount, req.direction, req.expiry_seconds
        )
        return result
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Pocket Option trade failed: {e}")


@app.post("/pocket-option/disconnect/{telegram_user_id}")
async def pocket_option_disconnect(telegram_user_id: str):
    await pocket_option_client.close_session(telegram_user_id)
    return {"status": "disconnected"}
