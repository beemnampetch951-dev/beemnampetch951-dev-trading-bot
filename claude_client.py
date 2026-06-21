# claude_client.py — Claude Vision API for chart analysis

import anthropic
import base64
import aiohttp
import os
from validators import TRADE_FIELDS

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EXTRACT_PROMPT = """คุณคือ AI ช่วยวิเคราะห์ chart การเทรด

จากรูป chart ที่ได้รับ ให้ extract ข้อมูลต่อไปนี้ (ถ้าเห็นชัดเจนเท่านั้น):
- asset: ชื่อคู่เงิน/ทรัพย์สิน (เช่น XAUUSD, BTCUSDT, NQ100, US30)
- position: Long หรือ Short
- entry_price: ราคา entry (ตัวเลขเท่านั้น)
- stop_loss: ราคา SL (ตัวเลขเท่านั้น)
- take_profit: ราคา TP (ตัวเลขเท่านั้น)
- timeframe: timeframe ของ chart (เช่น 15 min, 1H, 4H)
- bias: Bullish หรือ Bearish

ตอบเป็น JSON เท่านั้น ห้ามมี text อื่น ถ้าไม่แน่ใจ field ไหนให้ใส่ null
ตัวอย่าง: {"asset":"XAUUSD","position":"Long","entry_price":2345.50,"stop_loss":2330.00,"take_profit":2380.00,"timeframe":"15 min","bias":"Bullish"}"""

async def analyze_chart(image_url: str) -> dict:
    """Download รูปจาก Telegram แล้วส่ง Claude วิเคราะห์"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                image_data = await resp.read()
                content_type = resp.content_type or "image/jpeg"

        b64_image = base64.standard_b64encode(image_data).decode("utf-8")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64_image}},
                    {"type": "text", "text": EXTRACT_PROMPT}
                ]
            }]
        )

        import json
        text = response.content[0].text.strip()
        return json.loads(text)

    except Exception as e:
        print(f"[Claude] Error analyzing chart: {e}")
        return {}

async def smart_parse(user_text: str, current_data: dict) -> dict:
    """ใช้ Claude parse ข้อความที่ user พิมพ์มา extract ข้อมูลเทรด"""
    prompt = f"""Extract trading info จากข้อความนี้เป็น JSON:
ข้อความ: "{user_text}"
ข้อมูลที่มีอยู่แล้ว: {current_data}

Fields ที่ต้องการ: asset, position, bias, session, timeframe, strategy, entry_price, stop_loss, take_profit, risk_pct, outcome, profit, emotion, mistake, notes, time_entry, portfolio, account_type

ตอบ JSON เท่านั้น เฉพาะ field ที่พบในข้อความ ถ้าไม่มีให้ข้าม
ตัวอย่าง: {{"asset":"XAUUSD","position":"Long","outcome":"✅ Win","profit":250}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        import json
        text = response.content[0].text.strip()
        text = text.replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Claude] smart_parse error: {e}")
        return {}
