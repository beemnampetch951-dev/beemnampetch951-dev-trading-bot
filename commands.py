# commands.py — Bot commands handler

from telegram import Update
from telegram.ext import ContextTypes
from notion_client_wrapper import get_trade_stats, get_last_trades
from state_manager import StateManager, BotMode

state_mgr = StateManager()

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Trading Journal Bot*\n\n"
        "📌 *คำสั่งทั้งหมด:*\n\n"
        "🔹 *บันทึกเทรด*\n"
        "  /trade — เริ่มบันทึกเทรดใหม่\n"
        "  ส่งรูป chart — วิเคราะห์และบันทึกอัตโนมัติ\n\n"
        "🔹 *บันทึก Investment*\n"
        "  /invest — บันทึกการลงทุนหุ้น/crypto\n\n"
        "🔹 *ดูสถิติ*\n"
        "  /stats — สรุปสถิติรวม\n"
        "  /last — ดู 5 เทรดล่าสุด\n"
        "  /summary — สรุปประจำสัปดาห์\n\n"
        "🔹 *อื่นๆ*\n"
        "  /cancel — ยกเลิกการบันทึก\n"
        "  /help — ดูคำสั่งทั้งหมด\n\n"
        "💡 *วิธีใช้งาน:*\n"
        "ส่งรูป chart มาได้เลย bot จะ extract ข้อมูลให้อัตโนมัติ แล้วถามข้อมูลที่เหลือทีละ field จนครบ"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ กำลังดึงข้อมูลจาก Notion...")
    stats = await get_trade_stats()
    if not stats:
        await update.message.reply_text("❌ ดึงข้อมูลไม่ได้ ลองใหม่อีกครั้งครับ")
        return

    emoji_wr = "🟢" if stats["winrate"] >= 60 else "🟡" if stats["winrate"] >= 45 else "🔴"
    pnl_emoji = "📈" if stats["total_pnl"] >= 0 else "📉"

    text = (
        f"📊 *สถิติรวมทั้งหมด*\n"
        f"{'─'*25}\n"
        f"{emoji_wr} Win Rate: *{stats['winrate']}%*\n"
        f"✅ Win: *{stats['wins']}* ครั้ง\n"
        f"❌ Lose: *{stats['losses']}* ครั้ง\n"
        f"📋 Total: *{stats['total']}* เทรด\n"
        f"{'─'*25}\n"
        f"{pnl_emoji} Total P&L: *${stats['total_pnl']:,.2f}*\n"
        f"💵 Avg/trade: *${stats['avg_profit']:,.2f}*\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ กำลังดึงเทรดล่าสุด...")
    trades = await get_last_trades(5)
    if not trades:
        await update.message.reply_text("ยังไม่มีข้อมูลเทรดครับ")
        return

    lines = ["📋 *5 เทรดล่าสุด*\n" + "─"*25]
    for i, t in enumerate(trades, 1):
        outcome_icon = "✅" if "Win" in str(t["outcome"]) else "❌"
        pnl = f"${t['profit']:+,.2f}" if t["profit"] is not None else "—"
        lines.append(f"{i}. {outcome_icon} *{t['asset']}* | {pnl}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ กำลังสรุปผล...")
    stats = await get_trade_stats()
    trades = await get_last_trades(50)

    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)

    text = (
        f"📅 *Weekly Summary*\n"
        f"{'─'*25}\n"
        f"📊 ภาพรวมทั้งหมด\n"
        f"🏆 Win Rate: *{stats.get('winrate', 0)}%*\n"
        f"💰 Total P&L: *${stats.get('total_pnl', 0):,.2f}*\n"
        f"📋 Total Trades: *{stats.get('total', 0)}*\n"
        f"{'─'*25}\n"
        f"🔗 ดูรายละเอียดเพิ่มเติมใน Notion ได้เลยครับ"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state_mgr.reset(user_id)
    await update.message.reply_text(
        "❌ ยกเลิกการบันทึกแล้วครับ\n\n"
        "พิมพ์ /trade เพื่อเริ่มใหม่ หรือส่งรูป chart มาได้เลย"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)
