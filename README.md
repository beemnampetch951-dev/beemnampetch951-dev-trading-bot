# 🤖 Trading Journal Bot

Telegram bot บันทึกเทรดและ investment ลง Notion อัตโนมัติ พร้อม Claude Vision วิเคราะห์ chart

## Setup

### 1. Clone & Install
```bash
git clone <your-repo>
cd trading-bot
pip install -r requirements.txt
```

### 2. ตั้งค่า Environment Variables
```bash
cp .env.example .env
# แก้ไขค่าใน .env
```

| Variable | วิธีหา |
|---|---|
| `TELEGRAM_BOT_TOKEN` | คุยกับ @BotFather → /newbot |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `NOTION_API_KEY` | notion.so/my-integrations → New integration |
| `NOTION_BACKTEST_DB_ID` | เปิด database ใน Notion → copy ID จาก URL |
| `ALLOWED_USER_ID` | ส่ง /start ให้ @userinfobot → copy ID |

### 3. เชื่อม Notion Integration กับ Database
1. ไปที่ notion.so/my-integrations
2. สร้าง integration ใหม่
3. Copy API key ใส่ .env
4. เปิด Notion database → ⋯ → Add connections → เลือก integration ที่สร้าง

### 4. รันบนเครื่อง
```bash
python bot.py
```

### 5. Deploy บน Railway
1. Push code ขึ้น GitHub
2. ไปที่ railway.app → New Project → Deploy from GitHub
3. เพิ่ม Environment Variables ทุกตัวใน Railway dashboard
4. Railway จะ deploy อัตโนมัติ ✅

## คำสั่งทั้งหมด

| คำสั่ง | ฟังก์ชัน |
|---|---|
| ส่งรูป chart | วิเคราะห์ chart และเริ่มบันทึกเทรด |
| `/trade` | เริ่มบันทึกเทรดใหม่แบบ manual |
| `/invest` | บันทึกการลงทุนหุ้น/crypto |
| `/stats` | ดูสถิติรวม winrate และ P&L |
| `/last` | ดู 5 เทรดล่าสุด |
| `/summary` | สรุปผลประจำสัปดาห์ |
| `/cancel` | ยกเลิกการบันทึก |

## Flow การทำงาน

```
ส่งรูป chart
    ↓
Claude Vision extract: asset, position, entry, SL, TP, TF
    ↓
Bot ถามข้อมูลที่เหลือทีละ field (มี keyboard ให้กด)
    ↓
เตือนถ้า field ไหนยังขาด
    ↓
แสดง summary → ยืนยัน → บันทึก Notion
    ↓
ส่งลิงก์ Notion กลับมา ✅
```
