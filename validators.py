# validators.py — Field validation and missing field detection

def _get_dynamic(field: str, fallback: list[str]) -> list[str]:
    """ดึง options จาก dynamic_options cache ถ้ามี ไม่งั้น fallback"""
    try:
        from dynamic_options import get_options
        opts = get_options(field)
        return opts if opts else fallback
    except ImportError:
        return fallback

TRADE_FIELDS = {
    "asset":        {"label": "ทรัพย์สิน/คู่เงิน",    "dynamic": "asset",     "options": ["XAUUSD","NQ100","US30","BTCUSDT","ETHUSDT","EURUSD","SOLUSDT"], "required": True},
    "portfolio":    {"label": "Portfolio",              "options": ["💰 Fund","₿ Binance","💵 Own Capital"], "required": True},
    "account_type": {"label": "Account Type",          "options": ["CFD","Crypto Futures","Crypto Spot"], "required": True},
    "position":     {"label": "Position",              "options": ["Long","Short"], "required": True},
    "bias":         {"label": "Bias",                  "options": ["Bullish","Bearish"], "required": True},
    "session":      {"label": "Session",               "options": ["London","New York","Tokyo","Sydney"], "required": True},
    "timeframe":    {"label": "Timeframe",             "options": ["1 min","5 min","15 min","30 min","1H","4H","D1"], "required": True},
    "strategy":     {"label": "Strategy",              "dynamic": "strategy",  "options": ["Macro Advance"], "required": True},
    "entry_price":  {"label": "Entry Price",           "type": "number", "required": True},
    "stop_loss":    {"label": "Stop Loss (SL)",        "type": "number", "required": True},
    "take_profit":  {"label": "Take Profit (TP)",      "type": "number", "required": True},
    "risk_pct":     {"label": "Risk %",                "type": "number", "required": True},
    "time_entry":   {"label": "เวลา Entry",            "type": "datetime", "required": True},
    "outcome":      {"label": "ผลลัพธ์",               "options": ["✅ Win","❌ Lose"], "required": True},
    "profit":       {"label": "Profit/Loss ($)",       "type": "number", "required": True},
    "emotion":      {"label": "Emotion",               "options": ["😌 Calm","😎 Confident","😤 FOMO","😰 Nervous","😵 Confused"], "required": False},
    "mistake":      {"label": "Mistake",               "options": ["None","Early Entry","Early Exit","Moved SL","Oversize","Chased Price","No Setup"], "required": False},
    "notes":        {"label": "Notes",                 "type": "text", "required": False},
}

INVESTMENT_FIELDS = {
    "asset_name":    {"label": "ชื่อหุ้น/Crypto",      "type": "text",   "required": True},
    "asset_class":   {"label": "ประเภท",               "options": ["🇹🇭 Thai Stock","🇺🇸 US Stock","₿ Crypto","🏦 ETF","📦 Commodity"], "required": True},
    "portfolio":     {"label": "Portfolio",             "options": ["💰 Fund","₿ Binance","💵 Own Capital"], "required": True},
    "buy_reason":    {"label": "เหตุผลที่ซื้อ",         "type": "text",   "required": True},
    "buy_price":     {"label": "ราคาที่ซื้อ",           "type": "number", "required": True},
    "qty":           {"label": "จำนวน (Qty/Lot)",       "type": "number", "required": True},
    "target_price":  {"label": "ราคาเป้าหมาย (TP)",    "type": "number", "required": True},
    "cut_loss":      {"label": "ราคา Cut Loss (SL)",    "type": "number", "required": True},
    "conviction":    {"label": "Conviction",            "options": ["🔥 High","👍 Medium","🤔 Low"], "required": True},
    "sector":        {"label": "Sector",                "options": ["Tech","Finance","Energy","Health","Consumer","Crypto","Other"], "required": False},
    "notes":         {"label": "Notes",                 "type": "text",   "required": False},
}

def get_missing_required(data: dict, field_schema: dict) -> list[str]:
    """คืน list ของ field ที่ required แต่ยังไม่มีข้อมูล"""
    return [
        meta["label"]
        for key, meta in field_schema.items()
        if meta.get("required") and not data.get(key)
    ]

def format_missing_warning(missing: list[str]) -> str:
    """สร้างข้อความเตือน field ที่ขาด"""
    if not missing:
        return ""
    lines = ["⚠️ *ยังขาดข้อมูลต่อไปนี้:*\n"]
    for i, f in enumerate(missing, 1):
        lines.append(f"  {i}. {f}")
    lines.append("\nกรุณาเพิ่มข้อมูลหรือพิมพ์ /skip เพื่อข้ามได้ครับ")
    return "\n".join(lines)

def validate_number(value: str) -> float | None:
    """ตรวจสอบว่าเป็นตัวเลขหรือเปล่า"""
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None

def validate_datetime(value: str) -> str | None:
    """ตรวจสอบ format datetime เช่น 2025-03-15 14:30 หรือ 14:30"""
    from datetime import datetime
    formats = [
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M", "%H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            if fmt == "%H:%M":
                now = datetime.now()
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None

def compute_rr(entry: float, sl: float, tp: float, position: str) -> float | None:
    """คำนวณ Risk:Reward ratio"""
    try:
        if position.lower() == "long":
            risk   = entry - sl
            reward = tp - entry
        else:
            risk   = sl - entry
            reward = entry - tp
        if risk <= 0:
            return None
        return round(reward / risk, 2)
    except Exception:
        return None
