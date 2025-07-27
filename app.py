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


# 暫存上一輪搜尋結果 (單用戶測試用)
last_results = []

def get_images(keyword):
    """模糊搜尋：輸入的每個字元都必須出現在關鍵字欄位，不要求順序與連續"""
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
                    "no": row["編號"],
                    "keyword": row["關鍵字"],
                    "url": row["圖片網址"],
                    "episode": row["集數"]
                })
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
    global last_results
    user_input = event.message.text.strip()

    # 處理「輸入純數字」的情況
    if user_input.isdigit() and last_results:
        # 嘗試將此純數字當作圖片編號
        selected = [r for r in last_results if r["no"] == user_input]
        if selected:
            # 找到對應的圖片，回覆圖片與集數
            data = selected[0]
            img_url = data["url"]
            episode = data["episode"]
            msgs = [
                ImageSendMessage(
                    original_content_url=img_url,
                    preview_image_url=img_url
                ),
                TextSendMessage(
                    text=f"圖片編號：{data['no']}\n關鍵字：{data['keyword']}\n出處集數：{episode}"
                )
            ]
            line_bot_api.reply_message(event.reply_token, msgs)
            return
        # 沒有匹配到編號 -> 直接當作關鍵字進行搜尋

    # 關鍵字搜尋
    results = get_images(user_input)
    if results:
        last_results = results
        # 回傳清單文字
        lines = ["請輸入編號以查看圖片："]
        for data in results[:10]:  # 最多顯示 10 筆
            lines.append(f"{data['no']}. {data['keyword']}")
        reply_text = "\n".join(lines)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    else:
        last_results = []
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="沒有這張圖片餒！")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

