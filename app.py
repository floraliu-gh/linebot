from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    ImageSendMessage,
    AudioSendMessage,
)
import random
import os, requests, csv, traceback
from io import StringIO
import tempfile
from mutagen import File as MutagenFile

app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Google Sheet CSV 連結
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1FoDBb7Vk8OwoaIrAD31y5hA48KPBN91yTMRnuVMHktQ/export?format=csv"

# 用 dict 來存不同使用者的搜尋結果
user_cache = {}  # { user_id: [ {no, keyword, url, episode, audio}, ... ] }


def get_audio_duration_ms(url):
    """下載音檔並用 mutagen 計算長度（毫秒）。失敗則回傳 5000 ms"""
    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        # 用暫存檔存起來給 mutagen 讀取
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            tmp.write(res.content)
            tmp.flush()
            audio = MutagenFile(tmp.name)
            if audio and audio.info:
                return int(audio.info.length * 1000)
    except Exception as e:
        print("Error calculating audio duration:", e)
    return 3000


def get_images(keyword):
    """搜尋 Google Sheet，回傳符合條件的多筆資料"""
    try:
        # 假設 SHEET_CSV_URL 已在程式其他地方定義
        res = requests.get(SHEET_CSV_URL)
        res.raise_for_status()
        decoded_content = res.content.decode("utf-8-sig")
        f = StringIO(decoded_content)
        reader = csv.DictReader(f)

        results = []
        rows = list(reader)
        
        # 清理關鍵字：移除空白並轉小寫
        keyword_clean = keyword.replace(" ", "").lower()

        if not keyword_clean:
            return []

        # 判斷是否為隨機指令
        random_pick = keyword_clean in ["隨機", "🎲", "random"]
        use_artist = keyword_clean.startswith("/") or keyword_clean.startswith("∕") or keyword_clean.startswith("／")

        if random_pick:
            candidates = []
            for row in rows:
                url = row.get("圖片網址", "").strip()

                if url:
                    candidates.append({
                        "no": row["編號"],
                        "keyword": row["關鍵字"],
                        "url": url,
                        "episode": row["集數資訊"],
                        "audio": row.get("音檔", "").strip(),
                        "artist": row["藝人"]
                    })
            
            # 如果有候選名單，隨機回傳一筆；否則回傳空列表
            if candidates:
                return [random.choice(candidates)]
            return []

        # 如果是藝人搜尋，移除開頭的符號
        if use_artist:
            keyword_clean = keyword_clean[1:]
        
        for row in rows:
            # 根據模式選擇要比對的欄位
            if use_artist:
                target_text = row.get("藝人", "").strip().lower()
            else:
                target_text = row.get("關鍵字", "").strip().lower()
            
            # 模糊搜尋邏輯 (每個字都要包含在目標字串中)
            if all(ch in target_text for ch in keyword_clean):
                results.append({
                    "no": row["編號"],
                    "keyword": row["關鍵字"],
                    "url": row["圖片網址"],
                    "episode": row["集數資訊"],
                    "audio": row.get("音檔", "").strip(),
                    "artist": row["藝人"]
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

    last_results = user_cache.get(user_id, [])

    # 如果輸入純數字，表示從上一輪結果選擇
    if user_input.isdigit():
        if last_results:
            selected = [r for r in last_results if r["no"] == user_input]
            if selected:
                data = selected[0]
                msgs = [
                    ImageSendMessage(
                        original_content_url=data["url"],
                        preview_image_url=data["url"]
                    ),
                    TextSendMessage(
                        text=f"集數資訊：{data['episode']}"
                    )
                ]
                # 如果有音檔
                if data.get("audio"):
                    duration = get_audio_duration_ms(data["audio"])
                    msgs.append(
                        AudioSendMessage(
                            original_content_url=data["audio"],
                            duration=duration
                        )
                    )
                line_bot_api.reply_message(event.reply_token, msgs)
                return
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="沒有這張圖片餒！")
        )
        return

    # 文字關鍵字搜尋
    results = get_images(user_input)
    if results:
        user_cache[user_id] = results

        # 一筆結果直接回覆
        if len(results) == 1:
            data = results[0]
            msgs = [
                ImageSendMessage(
                    original_content_url=data["url"],
                    preview_image_url=data["url"]
                ),
                TextSendMessage(
                    text=f"集數資訊：{data['episode']}"
                )
            ]
            if data.get("audio"):
                duration = get_audio_duration_ms(data["audio"])
                msgs.append(
                    AudioSendMessage(
                        original_content_url=data["audio"],
                        duration=duration
                    )
                )
            line_bot_api.reply_message(event.reply_token, msgs)
            return

        # 多筆結果只回清單
        lines = ["請輸入圖片編號以查看圖片："]
        for data in results[:50]: 
            lines.append(f"{data['no']}. {data['keyword']}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="\n".join(lines))
        )
    else:
        user_cache[user_id] = []
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="沒有這張圖片餒！")
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
