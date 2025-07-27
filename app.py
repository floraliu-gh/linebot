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
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1FoDBb7Vk8OwoaIrAD31y5hA48KPBN91yTMRnuVMHktQ/export?format=csv"


# 用 dict 來存不同使用者的搜尋結果
user_cache = {}  # { user_id: [ {no, keyword, url, episode}, ... ] }

def get_images(keyword):
    try:
        res = requests.get(SHEET_CSV_URL)
        res.raise_for_status()
        res.encoding = "utf-8"
        f = StringIO(res.text)
        reader = csv.DictReader(f)

        results = []
        keyword_clean = keyword.replace(" ", "").lower()

        for row in reader:
            kw = row["關鍵字"].strip().lower()
            # 每個字元都必須存在於 kw
            if all(ch in kw for ch in keyword_clean):
                results.append({
                    "no": row["圖片編號"],
                    "keyword": row["關鍵字"],
                    "url": row["圖片網址"],
                    "episode": row["集數"]
                })
        return results
    except Exception:
        traceback.print_exc()
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
    user_id = event.source.user_id
    user_input = event.message.text.strip()

    # 從快取讀取使用者的前次結果
    last_results = user_cache.get(user_id, [])

    # 輸入純數字 -> 查詢上一輪的結果
    if user_input.isdigit() and last_results:
        selected = [r for r in last_results if r["no"] == user_input]
        if selected:
            data = selected[0]
            msgs = [
                ImageSendMessage(
                    original_content_url=data["url"],
                    preview_image_url=data["url"]
                ),
                TextSendMessage(
                    text=f"圖片編號：{data['no']}\n關鍵字：{data['keyword']}\n出處集數：{data['episode']}"
                )
            ]
            line_bot_api.reply_message(event.reply_token, msgs)
            return

    # 關鍵字搜尋
    results = get_images(user_input)
    if results:
        # 記住這個使用者最新的搜尋結果
        user_cache[user_id] = results
        lines = ["請輸入圖片編號以查看圖片："]
        for data in results[:10]:
            lines.append(f"{data['no']}. {data['keyword']}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="\n".join(lines))
        )
    else:
        # 清掉快取
        user_cache[user_id] = []
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="沒有這個梗圖餒！")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

