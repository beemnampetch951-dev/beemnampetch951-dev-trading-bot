# notion_client.py — Notion API handler

import os
from datetime import datetime
from notion_client import AsyncClient  # type: ignore
from validators import compute_rr

notion = AsyncClient(auth=os.getenv("NOTION_API_KEY"))
BACKTEST_DB = os.getenv("NOTION_BACKTEST_DB_ID")
INVESTMENT_DB = os.getenv("NOTION_INVESTMENT_DB_ID")

def _sel(value: str) -> dict:
    return {"select": {"name": value}}

def _multi(values: list[str]) -> dict:
    return {"multi_select": [{"name": v} for v in values]}

def _num(value) -> dict:
    try:
        return {"number": float(value)}
    except Exception:
        return {"number": None}

def _text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": str(value)}}]}

def _date(value: str) -> dict:
    return {"date": {"start": value}}

def _url(value: str) -> dict:
    return {"url": value}

def _title(value: str) -> dict:
    return {"title": [{"text": {"content": str(value)}}]}

async def save_trade(data: dict, screenshot_url: str | None = None) -> str | None:
    """บันทึก trade ลง Backtest (T) database"""
    try:
        # คำนวณ RR อัตโนมัติ
        rr = compute_rr(
            entry=float(data.get("entry_price", 0)),
            sl=float(data.get("stop_loss", 0)),
            tp=float(data.get("take_profit", 0)),
            position=data.get("position", "long")
        )

        # สร้างชื่อ trade อัตโนมัติ
        trade_name = f"{data.get('asset','?')} {data.get('position','?')} — {datetime.now().strftime('%d/%m/%Y %H:%M')}"

        props = {
            "Name": _title(trade_name),
            "Date": _date(datetime.now().strftime("%Y-%m-%d")),
            "ทรัพย์สิน/คู่เงิน": _sel(data.get("asset", "")),
            "Portfolio": _sel(data.get("portfolio", "")),
            "Account Type": _sel(data.get("account_type", "")),
            "Asset Class": _sel(data.get("asset_class", "")),
            "Position": _sel(data.get("position", "")),
            "Bias": _sel(data.get("bias", "")),
            "Session": _sel(data.get("session", "")),
            "Timeframe": _sel(data.get("timeframe", "")),
            "Strategy": _sel(data.get("strategy", "Macro Advance")),
            "Entry Price": _num(data.get("entry_price")),
            "Stop Loss": _num(data.get("stop_loss")),
            "Take Profit": _num(data.get("take_profit")),
            "Risk %": _num(data.get("risk_pct")),
            "Outcome": _sel(data.get("outcome", "")),
            "Profit": _num(data.get("profit")),
            "Emotion": _sel(data.get("emotion", "")),
            "Notes": _text(data.get("notes", "")),
        }

        if rr:
            props["RR"] = _num(rr)

        if data.get("time_entry"):
            props["Time entry"] = _date(data["time_entry"])

        if data.get("mistake"):
            mistakes = data["mistake"] if isinstance(data["mistake"], list) else [data["mistake"]]
            props["Mistake"] = _multi(mistakes)

        if screenshot_url:
            props["Screenshot"] = _url(screenshot_url)

        response = await notion.pages.create(
            parent={"database_id": BACKTEST_DB},
            properties=props
        )
        return response["url"]

    except Exception as e:
        print(f"[Notion] save_trade error: {e}")
        return None

async def save_investment(data: dict, screenshot_url: str | None = None) -> str | None:
    """บันทึก investment ลง Investment Log database"""
    try:
        asset_name = data.get("asset_name", "Unknown")
        props = {
            "Stock / Asset": _title(asset_name),
            "Asset Class": _sel(data.get("asset_class", "")),
            "Portfolio": _sel(data.get("portfolio", "")),
            "Status": _sel("🟢 Holding"),
            "Buy Reason": _text(data.get("buy_reason", "")),
            "Buy Price": _num(data.get("buy_price")),
            "Qty / Lot": _num(data.get("qty")),
            "Target Price": _num(data.get("target_price")),
            "Cut Loss Price": _num(data.get("cut_loss")),
            "Conviction": _sel(data.get("conviction", "")),
            "Notes": _text(data.get("notes", "")),
        }

        if data.get("sector"):
            props["Sector"] = _sel(data["sector"])

        if data.get("total_cost"):
            props["Total Cost"] = _num(data["total_cost"])
        elif data.get("buy_price") and data.get("qty"):
            props["Total Cost"] = _num(float(data["buy_price"]) * float(data["qty"]))

        if screenshot_url:
            props["Screenshot"] = _url(screenshot_url)

        response = await notion.pages.create(
            parent={"database_id": INVESTMENT_DB},
            properties=props
        )
        return response["url"]

    except Exception as e:
        print(f"[Notion] save_investment error: {e}")
        return None

async def get_trade_stats() -> dict:
    """ดึงสถิติจาก Backtest (T) database"""
    try:
        results = await notion.databases.query(database_id=BACKTEST_DB)
        trades = results.get("results", [])

        wins = [t for t in trades if t["properties"].get("Outcome", {}).get("select", {}).get("name") == "✅ Win"]
        total = len(trades)
        winrate = round(len(wins) / total * 100, 1) if total else 0

        profits = []
        for t in trades:
            p = t["properties"].get("Profit", {}).get("number")
            if p is not None:
                profits.append(p)

        total_pnl = sum(profits)
        avg_profit = round(total_pnl / len(profits), 2) if profits else 0

        return {
            "total": total,
            "wins": len(wins),
            "losses": total - len(wins),
            "winrate": winrate,
            "total_pnl": round(total_pnl, 2),
            "avg_profit": avg_profit,
        }

    except Exception as e:
        print(f"[Notion] get_stats error: {e}")
        return {}

async def get_last_trades(n: int = 5) -> list[dict]:
    """ดึง trade ล่าสุด n รายการ"""
    try:
        results = await notion.databases.query(
            database_id=BACKTEST_DB,
            sorts=[{"property": "Date", "direction": "descending"}],
            page_size=n
        )
        trades = []
        for t in results.get("results", []):
            p = t["properties"]
            trades.append({
                "name": p.get("Name", {}).get("title", [{}])[0].get("text", {}).get("content", "—"),
                "outcome": p.get("Outcome", {}).get("select", {}).get("name", "—"),
                "profit": p.get("Profit", {}).get("number"),
                "asset": p.get("ทรัพย์สิน/คู่เงิน", {}).get("select", {}).get("name", "—"),
            })
        return trades
    except Exception as e:
        print(f"[Notion] get_last_trades error: {e}")
        return []
