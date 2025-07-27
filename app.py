from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
import os, requests, csv, random
from io import StringIO

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Google Sheet CSV 連結，確保分享設定是「任何有連結的人都可以檢視」
# 並且網址類似：https://docs.google.com/spreadsheets/d/你的ID/export?format=csv
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1FoDBb7Vk8OwoaIrAD31y5hA48KPBN91yTMRnuVMHktQ/edit?usp=sharing"

def get_images(keyword):
    try:
        res = requests.get(SHEET_CSV_URL)
        res.raise_for_status()
        res.encoding = "utf-8"
        f = StringIO(res.text)
        reader = csv.DictReader(f)
        # 篩選 keyword 欄位值等於使用者輸入（可做忽略大小寫）
        urls = [row["image_url"] for row in reader if row["keyword"].strip().lower() == keyword.lower()]
        return urls
    except Exception as e:
        print("Error fetching or parsing CSV:", e)
        return []

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    keyword = event.message.text.strip()
    urls = get_images(keyword)
    if urls:
        img_url = random.choice(urls)
        msg = ImageSendMessage(
            original_content_url=img_url,
            preview_image_url=img_url
        )
    else:
        msg = TextSendMessage(text="沒有這個梗圖餒！")
    line_bot_api.reply_message(event.reply_token, msg)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

