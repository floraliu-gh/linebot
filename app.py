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
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1FoDBb7Vk8OwoaIrAD31y5hA48KPBN91yTMRnuVMHktQ/export?format=csv"


def get_images(keyword):
    ""從 Google Sheet 取得符合關鍵字的圖片與集數資料""
    try:
        res = requests.get(SHEET_CSV_URL)
        res.raise_for_status()
        res.encoding = "utf-8"
        f = StringIO(res.text)
        reader = csv.DictReader(f)

        # 模糊搜尋：只要「關鍵字」欄位包含使用者輸入文字
        results = [
            {"url": row["圖片網址"], "episode": row["集數資訊"]}
            for row in reader
            if keyword.lower() in row["關鍵字"].strip().lower()
        ]
        return results
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
    results = get_images(keyword)
    if results:
        chosen = random.choice(results)
        img_url = chosen["url"]
        episode = chosen["episode"]

        # 回覆：先傳圖片，再傳集數
        msgs = [
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url=img_url
            ),
            TextSendMessage(text=f"集數資訊：{episode}")
        ]
    else:
        msgs = [TextSendMessage(text="沒有這個梗圖餒！")]

    line_bot_api.reply_message(event.reply_token, msgs)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

