from flask import Flask, request, render_template
from dotenv import load_dotenv
import os, sqlite3, re, datetime
import pytesseract
from PIL import Image
import requests
from io import BytesIO

from linebot import LineBotApi, WebhookHandler
from linebot.models import *
from linebot.exceptions import InvalidSignatureError

load_dotenv()
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))
os.makedirs("static/images", exist_ok=True)

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            house_no TEXT,
            month TEXT,
            year TEXT,
            has_300baht INTEGER,
            image_path TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
init_db()

@app.route("/")
def index():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM records ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return render_template("index.html", rows=rows)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK", 200

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    message_id = event.message.id
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    image_name = f"{user_id}_{timestamp}.jpg"
    image_path = f"static/images/{image_name}"

    content = line_bot_api.get_message_content(message_id)
    image_data = BytesIO()
    for chunk in content.iter_content():
        image_data.write(chunk)
    with open(image_path, 'wb') as f:
        f.write(image_data.getvalue())

    image = Image.open(image_path)
    text = pytesseract.image_to_string(image, lang='tha')
    has_300baht = 1 if "300" in text and "บาท" in text else 0

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกรูปแล้ว กำลังรอข้อความ..."))

    with sqlite3.connect("database.db") as conn:
        conn.execute("INSERT INTO records (user_id, house_no, month, year, has_300baht, image_path, timestamp) VALUES (?, '', '', '', ?, ?, ?)",
                     (user_id, has_300baht, image_path, timestamp))
        conn.commit()

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    match = re.search(r"(?P<house>\d+/\d+)\s+(?P<month>[ก-๙]+)\s+(?P<year>\d+)", text)
    if match:
        house = match.group("house")
        month = match.group("month")
        year = match.group("year")

        with sqlite3.connect("database.db") as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM records WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
            last = c.fetchone()
            if last:
                c.execute("UPDATE records SET house_no=?, month=?, year=? WHERE id=?", (house, month, year, last[0]))
                conn.commit()

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ข้อมูลบันทึกเรียบร้อย"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รูปแบบข้อความไม่ถูกต้อง เช่น 39/50 พค 68"))

if __name__ == "__main__":
    app.run(debug=True)
