"""
MT5 connection via MetaApi (https://metaapi.cloud).

Requires METAAPI_TOKEN env var — this is separate from the user's broker
credentials. MetaApi provisions a cloud MT5 terminal per account.

NOTE: Provisioning a new MetaApi account takes ~1-3 minutes the first time
a user connects (deploying the cloud terminal). Subsequent calls reuse it.
"""
import os
from metaapi_cloud_sdk import MetaApi

METAAPI_TOKEN = os.environ.get("METAAPI_TOKEN", "")
_api = MetaApi(METAAPI_TOKEN) if METAAPI_TOKEN else None

# Cache of provisioned MetaApi account IDs, keyed by telegram_user_id
_account_cache: dict[str, str] = {}


async def _get_or_create_account(telegram_user_id: str, broker: str, login: str, password: str):
    if not _api:
        raise RuntimeError("METAAPI_TOKEN not configured")

    if telegram_user_id in _account_cache:
        account_id = _account_cache[telegram_user_id]
        return await _api.metatrader_account_api.get_account(account_id)

    account = await _api.metatrader_account_api.create_account({
        "name": f"jeffsbot-{telegram_user_id}",
        "type": "cloud",
        "login": login,
        "password": password,
        "server": broker,
        "platform": "mt5",
        "magic": 0,
    })
    await account.deploy()
    await account.wait_connected()
    _account_cache[telegram_user_id] = account.id
    return account


async def get_account_info(telegram_user_id: str, broker: str, login: str, password: str) -> dict:
    account = await _get_or_create_account(telegram_user_id, broker, login, password)
    connection = account.get_rpc_connection()
    await connection.connect()
    await connection.wait_synchronized()
    info = await connection.get_account_information()
    positions = await connection.get_positions()
    return {"account_info": info, "positions": positions}


async def place_trade(
    telegram_user_id: str,
    broker: str,
    login: str,
    password: str,
    symbol: str,
    volume: float,
    order_type: str,  # "ORDER_TYPE_BUY" or "ORDER_TYPE_SELL"
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    account = await _get_or_create_account(telegram_user_id, broker, login, password)
    connection = account.get_rpc_connection()
    await connection.connect()
    await connection.wait_synchronized()

    if order_type == "ORDER_TYPE_BUY":
        result = await connection.create_market_buy_order(symbol, volume, stop_loss, take_profit)
    elif order_type == "ORDER_TYPE_SELL":
        result = await connection.create_market_sell_order(symbol, volume, stop_loss, take_profit)
    else:
        raise ValueError("order_type must be ORDER_TYPE_BUY or ORDER_TYPE_SELL")

    return result
