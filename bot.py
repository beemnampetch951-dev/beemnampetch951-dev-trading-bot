# bot.py — Main Telegram Bot entry point (fixed all bugs)

import os
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from state_manager import StateManager, BotMode
from validators import (
    TRADE_FIELDS, INVESTMENT_FIELDS,
    get_missing_required, format_missing_warning,
    validate_number, validate_datetime
)
from claude_client import analyze_chart, smart_parse
from notion_client_wrapper import save_trade, save_investment
from commands import cmd_start, cmd_stats, cmd_last, cmd_summary, cmd_cancel, cmd_help

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
log = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
state_mgr = StateManager()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    if ALLOWED_USER_ID == 0:
        return True
    return update.effective_user.id == ALLOWED_USER_ID

def get_message(update: Update) -> Message:
    """ดึง message object ไม่ว่าจะมาจาก message หรือ callback_query"""
    if update.callback_query:
        return update.callback_query.message
    return update.message

def build_keyboard(options: list[str], cols: int = 2) -> InlineKeyboardMarkup:
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    keyboard = [[InlineKeyboardButton(o, callback_data=o) for o in row] for row in rows]
    return InlineKeyboardMarkup(keyboard)

def build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ บันทึก Notion", callback_data="__confirm__"),
        InlineKeyboardButton("✏️ แก้ไข", callback_data="__edit__"),
        InlineKeyboardButton("❌ ยกเลิก", callback_data="__cancel__"),
    ]])

def get_active_mode(state) -> str:
    """คืน 'trade' หรือ 'invest' จาก state"""
    if state.mode in (BotMode.TRADE_LOG, BotMode.AWAITING_CONFIRM, BotMode.AWAITING_EDIT):
        return "trade" if state.trade_data else "invest"
    if state.mode == BotMode.INVESTMENT_LOG:
        return "invest"
    return "trade"

# ─── Question order ───────────────────────────────────────────────────────────

TRADE_ORDER = [
    "asset", "portfolio", "account_type", "position", "bias",
    "session", "timeframe", "entry_price", "stop_loss", "take_profit",
    "risk_pct", "time_entry", "outcome", "profit", "emotion", "mistake", "notes"
]

INVEST_ORDER = [
    "asset_name", "asset_class", "portfolio", "buy_reason",
    "buy_price", "qty", "target_price", "cut_loss", "conviction", "sector", "notes"
]

def next_missing_field(data: dict, schema: dict, order: list[str]) -> str | None:
    for key in order:
        if key in schema and schema[key].get("required") and not data.get(key):
            return key
    return None

# ─── Summary formatters ───────────────────────────────────────────────────────

def format_trade_summary(data: dict) -> str:
    label_map = {k: v["label"] for k, v in TRADE_FIELDS.items()}
    lines = ["📋 *สรุปข้อมูลเทรด*\n" + "─"*25]
    for key in TRADE_ORDER:
        val = data.get(key)
        if val is not None and val != "":
            lines.append(f"• {label_map.get(key, key)}: *{val}*")

    # เช็ค missing required fields
    missing = get_missing_required(data, TRADE_FIELDS)
    if missing:
        lines.append("\n" + format_missing_warning(missing))
    return "\n".join(lines)

def format_investment_summary(data: dict) -> str:
    label_map = {k: v["label"] for k, v in INVESTMENT_FIELDS.items()}
    lines = ["📦 *สรุปข้อมูล Investment*\n" + "─"*25]
    for key in INVEST_ORDER:
        val = data.get(key)
        if val is not None and val != "":
            lines.append(f"• {label_map.get(key, key)}: *{val}*")

    missing = get_missing_required(data, INVESTMENT_FIELDS)
    if missing:
        lines.append("\n" + format_missing_warning(missing))
    return "\n".join(lines)

# ─── Core: ask next field ─────────────────────────────────────────────────────

async def ask_next_field(message: Message, user_id: int, mode: str):
    """ถาม field ถัดไปที่ยังขาด หรือแสดง summary ถ้าครบแล้ว"""
    state = state_mgr.get(user_id)

    if mode == "trade":
        data   = state.trade_data
        schema = TRADE_FIELDS
        order  = TRADE_ORDER
    else:
        data   = state.investment_data
        schema = INVESTMENT_FIELDS
        order  = INVEST_ORDER

    next_key = next_missing_field(data, schema, order)

    if next_key is None:
        # ✅ ครบทุก required field — แสดง summary + confirm
        summary = format_trade_summary(data) if mode == "trade" else format_investment_summary(data)
        await message.reply_text(
            summary + "\n\n─"*13 + "\n\nยืนยันบันทึกลง Notion มั้ยครับ? 👇",
            parse_mode="Markdown",
            reply_markup=build_confirm_keyboard()
        )
        state_mgr.set_mode(user_id, BotMode.AWAITING_CONFIRM)
        return

    meta  = schema[next_key]
    label = meta["label"]

    # ดึง options — ถ้ามี dynamic key ให้ดึงจาก dynamic_options
    if meta.get("dynamic"):
        from dynamic_options import get_options
        options = get_options(meta["dynamic"]) or meta.get("options", [])
    else:
        options = meta.get("options")

    # แสดง progress: กี่ field แล้ว
    filled  = sum(1 for k in order if k in schema and data.get(k))
    total_r = sum(1 for k in order if k in schema and schema[k].get("required"))
    progress = f"[{filled}/{total_r}]"

    if options:
        await message.reply_text(
            f"👇 *{label}* {progress}",
            parse_mode="Markdown",
            reply_markup=build_keyboard(options)
        )
    else:
        hints = {"number": "ตัวเลข เช่น 2345.50", "datetime": "เช่น 14:30 หรือ 2025-03-15 14:30", "text": "พิมพ์ข้อความ"}
        hint  = hints.get(meta.get("type", ""), "")
        await message.reply_text(
            f"✏️ *{label}* {progress}\n_{hint}_" if hint else f"✏️ *{label}* {progress}",
            parse_mode="Markdown"
        )

    state.current_field = next_key

# ─── Validate & set field value ───────────────────────────────────────────────

async def set_field_value(message: Message, user_id: int, field_key: str, raw_value: str, mode: str) -> bool:
    """ตรวจสอบ value แล้ว set ถ้า valid — คืน True ถ้าผ่าน False ถ้าไม่ผ่าน"""
    schema = TRADE_FIELDS if mode == "trade" else INVESTMENT_FIELDS
    if field_key not in schema:
        return True

    meta      = schema[field_key]
    field_type = meta.get("type", "")

    if field_type == "number":
        val = validate_number(raw_value)
        if val is None:
            await message.reply_text(f"⚠️ *{meta['label']}* ต้องเป็นตัวเลขครับ เช่น `2345.50`", parse_mode="Markdown")
            return False
        raw_value = val

    elif field_type == "datetime":
        val = validate_datetime(raw_value)
        if val is None:
            await message.reply_text(
                f"⚠️ *{meta['label']}* format ไม่ถูกต้องครับ\nลองพิมพ์แบบนี้: `14:30` หรือ `2025-03-15 14:30`",
                parse_mode="Markdown"
            )
            return False
        raw_value = val

    state = state_mgr.get(user_id)
    if mode == "trade":
        state.trade_data[field_key] = raw_value
    else:
        state.investment_data[field_key] = raw_value
    return True

# ─── Photo handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user_id = update.effective_user.id
    await update.message.reply_text("🔍 วิเคราะห์ chart อยู่นะครับ รอสักครู่...")

    photo    = update.message.photo[-1]
    file     = await context.bot.get_file(photo.file_id)
    image_url = file.file_path

    # ถ้ามีการบันทึกอยู่แล้ว reset ก่อน
    state = state_mgr.get(user_id)
    if state.mode not in (BotMode.IDLE, BotMode.TRADE_LOG):
        state_mgr.reset(user_id)

    state = state_mgr.get(user_id)
    state.screenshot_url = image_url
    state_mgr.set_mode(user_id, BotMode.TRADE_LOG)

    extracted = await analyze_chart(image_url)

    if extracted:
        for k, v in extracted.items():
            if v is not None:
                state.trade_data[k] = v

        # parse caption ด้วยถ้ามี
        if update.message.caption:
            extra = await smart_parse(update.message.caption, state.trade_data)
            for k, v in extra.items():
                if v is not None and not state.trade_data.get(k):
                    state.trade_data[k] = v

        found_labels = [TRADE_FIELDS[k]["label"] for k in extracted if extracted.get(k) is not None and k in TRADE_FIELDS]
        msg = "✅ *Extract ได้แล้ว:*\n" + "\n".join(f"  • {f}" for f in found_labels)
        await update.message.reply_text(msg + "\n\nมากรอกส่วนที่เหลือกันครับ 👇", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "⚠️ ไม่สามารถ extract ข้อมูลจากรูปได้ครับ\n"
            "ลองส่งรูปที่ชัดขึ้น หรือกรอกข้อมูลเองทีละ field ได้เลย 👇"
        )

    await ask_next_field(update.message, user_id, "trade")

# ─── Text message handler ─────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    user_id = update.effective_user.id
    text     = update.message.text.strip()
    state    = state_mgr.get(user_id)

    # ── IDLE: ลอง smart parse ──
    if state.mode == BotMode.IDLE:
        parsed = await smart_parse(text, {})
        if parsed and len(parsed) >= 2:
            state_mgr.set_mode(user_id, BotMode.TRADE_LOG)
            for k, v in parsed.items():
                if v is not None:
                    state.trade_data[k] = v
            await update.message.reply_text("✅ รับข้อมูลแล้วครับ มากรอกส่วนที่เหลือกัน 👇")
            await ask_next_field(update.message, user_id, "trade")
        else:
            await update.message.reply_text(
                "💡 *วิธีใช้งาน:*\n"
                "📸 ส่งรูป chart — วิเคราะห์อัตโนมัติ\n"
                "📝 /trade — บันทึกเทรดด้วยตัวเอง\n"
                "📦 /invest — บันทึกการลงทุน\n"
                "📊 /stats — ดูสถิติ",
                parse_mode="Markdown"
            )
        return

    # ── AWAITING_EDIT: แก้ไข field ──
    if state.mode == BotMode.AWAITING_EDIT:
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            field_name, new_value = parts
            mode = "trade" if state.trade_data else "invest"
            schema = TRADE_FIELDS if mode == "trade" else INVESTMENT_FIELDS

            # หา field key จากชื่อหรือ label
            matched_key = None
            for key, meta in schema.items():
                if key == field_name.lower() or meta["label"].lower() == field_name.lower():
                    matched_key = key
                    break

            if matched_key:
                ok = await set_field_value(update.message, user_id, matched_key, new_value, mode)
                if ok:
                    await update.message.reply_text(f"✅ แก้ไข *{schema[matched_key]['label']}* เป็น `{new_value}` แล้วครับ", parse_mode="Markdown")
                    # กลับไป summary
                    state_mgr.set_mode(user_id, BotMode.TRADE_LOG if mode == "trade" else BotMode.INVESTMENT_LOG)
                    await ask_next_field(update.message, user_id, mode)
            else:
                field_list = "\n".join(f"  `{k}` — {v['label']}" for k, v in schema.items())
                await update.message.reply_text(
                    f"❓ ไม่พบ field `{field_name}`\n\n*Fields ที่มี:*\n{field_list}",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text(
                "✏️ พิมพ์: `field_name ค่าใหม่`\nเช่น: `profit 350` หรือ `emotion 😌 Calm`",
                parse_mode="Markdown"
            )
        return

    # ── TRADE_LOG / INVESTMENT_LOG: กรอก field ปัจจุบัน ──
    mode = get_active_mode(state)
    current_field = state.current_field

    if current_field:
        ok = await set_field_value(update.message, user_id, current_field, text, mode)
        if not ok:
            return  # ให้ user พิมพ์ใหม่

    await ask_next_field(update.message, user_id, mode)

# ─── Callback query handler ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    query = update.callback_query
    await query.answer()

    user_id  = update.effective_user.id
    cb_data  = query.data
    state    = state_mgr.get(user_id)
    mode     = get_active_mode(state)

    if cb_data == "__confirm__":
        await query.edit_message_text("⏳ กำลังบันทึกลง Notion...")

        if mode == "trade":
            url = await save_trade(state.trade_data, state.screenshot_url)
            ok_msg  = f"✅ *บันทึกเทรดสำเร็จ!*\n\n🔗 [ดูใน Notion]({url})\n\nส่งรูป chart ต่อได้เลยครับ 📸"
            err_msg = "❌ บันทึกไม่สำเร็จ กรุณาลองใหม่อีกครั้งครับ"
        else:
            url = await save_investment(state.investment_data, state.screenshot_url)
            ok_msg  = f"✅ *บันทึก Investment สำเร็จ!*\n\n🔗 [ดูใน Notion]({url})"
            err_msg = "❌ บันทึกไม่สำเร็จ กรุณาลองใหม่อีกครั้งครับ"

        await context.bot.send_message(
            chat_id=user_id,
            text=ok_msg if url else err_msg,
            parse_mode="Markdown"
        )
        state_mgr.reset(user_id)

    elif cb_data == "__cancel__":
        state_mgr.reset(user_id)
        await query.edit_message_text("❌ ยกเลิกแล้วครับ\n\nพิมพ์ /trade หรือส่งรูป chart ใหม่ได้เลย")

    elif cb_data == "__edit__":
        # เข้า edit mode
        state_mgr.set_mode(user_id, BotMode.AWAITING_EDIT)
        schema = TRADE_FIELDS if mode == "trade" else INVESTMENT_FIELDS
        field_list = "\n".join(f"  `{k}` — {v['label']}" for k, v in schema.items())
        await query.edit_message_text(
            f"✏️ *แก้ไขข้อมูล*\n\nพิมพ์: `field_name ค่าใหม่`\n\n*Fields ที่แก้ไขได้:*\n{field_list}",
            parse_mode="Markdown"
        )

    else:
        # user กดเลือก option จาก keyboard
        current_field = state.current_field
        if current_field:
            if mode == "trade":
                state.trade_data[current_field] = cb_data
            else:
                state.investment_data[current_field] = cb_data

        await ask_next_field(query.message, user_id, mode)

# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    state_mgr.reset(user_id)
    state_mgr.set_mode(user_id, BotMode.TRADE_LOG)
    await update.message.reply_text(
        "📝 *เริ่มบันทึกเทรดใหม่*\n\n"
        "💡 ส่งรูป chart มาก่อนได้เลย — bot จะ extract ข้อมูลให้อัตโนมัติ\n"
        "หรือจะกรอกเองทีละ field ก็ได้ครับ 👇",
        parse_mode="Markdown"
    )
    await ask_next_field(update.message, user_id, "trade")

async def cmd_invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    state_mgr.reset(user_id)
    state_mgr.set_mode(user_id, BotMode.INVESTMENT_LOG)
    await update.message.reply_text(
        "📦 *บันทึก Investment ใหม่*\n\nมาเริ่มกันเลยครับ 👇",
        parse_mode="Markdown"
    )
    await ask_next_field(update.message, user_id, "invest")

async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ข้าม optional field ได้"""
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    state   = state_mgr.get(user_id)
    mode    = get_active_mode(state)

    if state.current_field:
        schema = TRADE_FIELDS if mode == "trade" else INVESTMENT_FIELDS
        meta   = schema.get(state.current_field, {})
        if meta.get("required"):
            await update.message.reply_text(
                f"⚠️ *{meta['label']}* เป็น required field ข้ามไม่ได้ครับ กรุณากรอกให้ครบ",
                parse_mode="Markdown"
            )
            return

    await update.message.reply_text("⏭ ข้ามแล้วครับ")
    if mode == "trade":
        state_mgr.set_mode(user_id, BotMode.TRADE_LOG)
    else:
        state_mgr.set_mode(user_id, BotMode.INVESTMENT_LOG)
    state.current_field = None
    await ask_next_field(update.message, user_id, mode)

# ─── Main ─────────────────────────────────────────────────────────────────────

async def post_init(application: Application):
    """sync options จาก Notion ตอน bot เริ่มทำงาน"""
    from dynamic_options import sync_options_from_notion
    await sync_options_from_notion()
    log.info("✅ Options synced from Notion")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # Core commands
    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("trade",        cmd_trade))
    app.add_handler(CommandHandler("invest",       cmd_invest))
    app.add_handler(CommandHandler("stats",        cmd_stats))
    app.add_handler(CommandHandler("last",         cmd_last))
    app.add_handler(CommandHandler("summary",      cmd_summary))
    app.add_handler(CommandHandler("cancel",       cmd_cancel))
    app.add_handler(CommandHandler("skip",         cmd_skip))

    # Dynamic option commands
    app.add_handler(CommandHandler("add_strategy", cmd_add_strategy))
    app.add_handler(CommandHandler("add_asset",    cmd_add_asset))
    app.add_handler(CommandHandler("options",      cmd_list_options))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info("🤖 Trading Bot v2.1 started — polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()


# ─── Dynamic option handlers (เพิ่มเข้ามาหลัง main) ─────────────────────────

async def cmd_add_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_strategy ชื่อ_strategy
    เพิ่ม strategy ใหม่เข้า Notion + สร้าง stat tracking row
    """
    if not is_allowed(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📌 *วิธีใช้:*\n`/add_strategy ชื่อ strategy`\n\nเช่น: `/add_strategy SMC Breaker`",
            parse_mode="Markdown"
        )
        return

    strategy_name = " ".join(args).strip()
    from dynamic_options import add_strategy_to_notion, is_known_option, get_options

    if is_known_option("strategy", strategy_name):
        current = get_options("strategy")
        await update.message.reply_text(
            f"ℹ️ Strategy *{strategy_name}* มีอยู่แล้วครับ\n\n"
            f"📋 *Strategies ทั้งหมด:*\n" + "\n".join(f"  • {s}" for s in current),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ กำลังเพิ่ม *{strategy_name}* เข้า Notion...", parse_mode="Markdown")
    ok = await add_strategy_to_notion(strategy_name)

    if ok:
        current = get_options("strategy")
        await update.message.reply_text(
            f"✅ เพิ่ม Strategy *{strategy_name}* สำเร็จ!\n\n"
            f"📊 Notion อัปเดตแล้ว:\n"
            f"  • Backtest (T) — Strategy options\n"
            f"  • Stat (T) — สร้าง tracking row ใหม่\n\n"
            f"📋 *Strategies ทั้งหมด ({len(current)} ตัว):*\n" +
            "\n".join(f"  {i+1}. {s}" for i, s in enumerate(current)),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ เพิ่มไม่สำเร็จ กรุณาลองใหม่อีกครั้งครับ")


async def cmd_add_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_asset ชื่อ_asset
    เพิ่ม asset ใหม่เข้า Notion Backtest (T)
    """
    if not is_allowed(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📌 *วิธีใช้:*\n`/add_asset ชื่อ asset`\n\nเช่น: `/add_asset GBPUSD` หรือ `/add_asset NVDA`",
            parse_mode="Markdown"
        )
        return

    asset_name = " ".join(args).strip().upper()
    from dynamic_options import add_asset_to_notion, is_known_option, get_options

    if is_known_option("asset", asset_name):
        current = get_options("asset")
        await update.message.reply_text(
            f"ℹ️ Asset *{asset_name}* มีอยู่แล้วครับ\n\n"
            f"📋 *Assets ทั้งหมด:*\n" + "\n".join(f"  • {a}" for a in current),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"⏳ กำลังเพิ่ม *{asset_name}* เข้า Notion...", parse_mode="Markdown")
    ok = await add_asset_to_notion(asset_name)

    if ok:
        current = get_options("asset")
        await update.message.reply_text(
            f"✅ เพิ่ม Asset *{asset_name}* สำเร็จ!\n\n"
            f"📋 *Assets ทั้งหมด ({len(current)} ตัว):*\n" +
            "\n".join(f"  {i+1}. {a}" for i, a in enumerate(current)),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ เพิ่มไม่สำเร็จ กรุณาลองใหม่อีกครั้งครับ")


async def cmd_list_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/options — แสดง strategy และ asset ทั้งหมดที่มี"""
    if not is_allowed(update):
        return

    from dynamic_options import get_options
    strategies = get_options("strategy")
    assets     = get_options("asset")

    text = (
        f"📋 *Options ทั้งหมด*\n"
        f"{'─'*25}\n\n"
        f"🧠 *Strategies ({len(strategies)} ตัว):*\n" +
        "\n".join(f"  {i+1}. {s}" for i, s in enumerate(strategies)) +
        f"\n\n🎯 *Assets ({len(assets)} ตัว):*\n" +
        "\n".join(f"  {i+1}. {a}" for i, a in enumerate(assets)) +
        f"\n\n{'─'*25}\n"
        f"➕ เพิ่มใหม่:\n"
        f"  `/add_strategy ชื่อ` — เพิ่ม strategy\n"
        f"  `/add_asset ชื่อ` — เพิ่ม asset"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
