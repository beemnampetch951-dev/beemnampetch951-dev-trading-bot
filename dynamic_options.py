# dynamic_options.py — Dynamic strategy/asset creation with Notion sync

import os
import json
import logging
from pathlib import Path
from notion_client import AsyncClient

log = logging.getLogger(__name__)

notion = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
BACKTEST_DB  = os.getenv("NOTION_BACKTEST_DB_ID")
STAT_DB      = os.getenv("NOTION_STAT_DB_ID")

# Local cache file — sync กับ Notion เมื่อ bot start
CACHE_FILE = Path("dynamic_options_cache.json")

# Default options ที่มีอยู่แล้ว
DEFAULT_OPTIONS = {
    "strategy": ["Macro Advance"],
    "asset":    ["XAUUSD", "NQ100", "US30", "BTCUSDT", "ETHUSDT", "EURUSD", "SOLUSDT"],
}

def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {k: list(v) for k, v in DEFAULT_OPTIONS.items()}

def _save_cache(data: dict):
    try:
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning(f"[DynOptions] cache save failed: {e}")

# In-memory options — โหลดจาก cache ตอน import
_options: dict[str, list[str]] = _load_cache()


# ─── Public API ───────────────────────────────────────────────────────────────

def get_options(field: str) -> list[str]:
    """ดึง options ปัจจุบันของ field นั้น"""
    return list(_options.get(field, []))

def is_known_option(field: str, value: str) -> bool:
    """เช็คว่า value นี้มีอยู่แล้วหรือเปล่า (case-insensitive)"""
    return any(v.lower() == value.lower() for v in _options.get(field, []))

def add_option_local(field: str, value: str):
    """เพิ่ม option เข้า in-memory cache และ save ไฟล์"""
    if field not in _options:
        _options[field] = []
    if not is_known_option(field, value):
        _options[field].append(value)
        _save_cache(_options)
        log.info(f"[DynOptions] Added '{value}' to '{field}'")

async def sync_options_from_notion():
    """โหลด options จาก Notion database ตอน bot start"""
    try:
        db = await notion.databases.retrieve(database_id=BACKTEST_DB)
        props = db.get("properties", {})

        for field_key, notion_prop in [
            ("strategy", "Strategy"),
            ("asset",    "ทรัพย์สิน/คู่เงิน"),
        ]:
            prop = props.get(notion_prop, {})
            notion_options = [o["name"] for o in prop.get("select", {}).get("options", [])]
            if notion_options:
                _options[field_key] = notion_options
                log.info(f"[DynOptions] Synced {field_key}: {notion_options}")

        _save_cache(_options)
    except Exception as e:
        log.warning(f"[DynOptions] sync failed (using cache): {e}")

async def add_strategy_to_notion(strategy_name: str) -> bool:
    """
    เพิ่ม strategy ใหม่เข้า:
    1. Notion Backtest (T) — strategy select options
    2. Notion Stat (T) — สร้าง stat tracking row
    """
    try:
        # 1. อ่าน options ปัจจุบันจาก Notion
        db = await notion.databases.retrieve(database_id=BACKTEST_DB)
        existing = db["properties"]["Strategy"]["select"]["options"]
        existing_names = [o["name"] for o in existing]

        if strategy_name in existing_names:
            add_option_local("strategy", strategy_name)
            return True

        # 2. เพิ่ม option ใหม่ใน Backtest DB
        new_options = existing + [{"name": strategy_name}]
        await notion.databases.update(
            database_id=BACKTEST_DB,
            properties={
                "Strategy": {
                    "select": {"options": new_options}
                }
            }
        )

        # 3. สร้าง stat tracking row ใน Stat (T)
        if STAT_DB:
            await notion.pages.create(
                parent={"database_id": STAT_DB},
                properties={
                    "Name": {"title": [{"text": {"content": strategy_name}}]},
                }
            )
            log.info(f"[DynOptions] Created Stat row for strategy: {strategy_name}")

        # 4. update local cache
        add_option_local("strategy", strategy_name)
        log.info(f"[DynOptions] Added strategy to Notion: {strategy_name}")
        return True

    except Exception as e:
        log.error(f"[DynOptions] add_strategy_to_notion error: {e}")
        return False

async def add_asset_to_notion(asset_name: str) -> bool:
    """เพิ่ม asset ใหม่เข้า Notion Backtest (T) select options"""
    try:
        db = await notion.databases.retrieve(database_id=BACKTEST_DB)
        existing = db["properties"]["ทรัพย์สิน/คู่เงิน"]["select"]["options"]
        existing_names = [o["name"] for o in existing]

        if asset_name in existing_names:
            add_option_local("asset", asset_name)
            return True

        new_options = existing + [{"name": asset_name}]
        await notion.databases.update(
            database_id=BACKTEST_DB,
            properties={
                "ทรัพย์สิน/คู่เงิน": {
                    "select": {"options": new_options}
                }
            }
        )

        add_option_local("asset", asset_name)
        log.info(f"[DynOptions] Added asset to Notion: {asset_name}")
        return True

    except Exception as e:
        log.error(f"[DynOptions] add_asset_to_notion error: {e}")
        return False
