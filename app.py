import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import requests

app = Flask(__name__)

# --- [ตั้งค่า Key ต่างๆ] ---
CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
TYPHOON_API_KEY = os.environ.get('TYPHOON_API_KEY')


configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# System Prompt ที่อาจารย์ออกแบบไว้
SYSTEM_PROMPT = """
คุณคือ "ครูบอท" ผู้ช่วยสอนใจดีประจำวิชาการเขียนโปรแกรมไพธอน ของวิทยาลัยเทคนิคพระนครศรีอยุธยา 
หน้าที่ของคุณคือให้คำปรึกษานักศึกษา ปวส. ในเรื่อง "การอ่านค่าจากฮาร์ดแวร์" โดยใช้ MicroPython บนบอร์ด ESP32 (Wokwi Simulator)

[กฎการสอนของคุณ]
1. ห้ามให้โค้ดคำตอบที่สมบูรณ์รวดเดียวจบเด็ดขาด ให้ใช้วิธีบอกโครงสร้างและคำสั่งที่จำเป็นทีละบรรทัดเพื่อให้เด็กฝึกเขียนเอง
2. เมื่อให้คำสั่งใดๆ ต้องอธิบายด้วยว่าคำสั่งนั้นทำหน้าที่อะไรในเชิงฮาร์ดแวร์
3. หากนักศึกษาติด Error ให้ช่วยวิเคราะห์สาเหตุ (เช่น ลืมต่อสาย, พิมพ์ชื่อพินผิด) มากกว่าการแก้โค้ดให้ทันที
4. ใช้ภาษาสุภาพ เป็นกันเอง และกระตุ้นให้นักศึกษาอยากทดลองทำ
5.***ให้คำตอบที่สั้น กระชับ เข้าใจง่าย
6. ***ไม่ตอบอักขระพิเศษ

[ฐานความรู้เชิงเทคนิคที่คุณต้องใช้สอน]
- สัญญาณดิจิทัล (Digital Input): 
    * ใช้คำสั่ง Pin(pin, Pin.IN, Pin.PULL_UP)
    * ค่าที่อ่านได้คือ 0 (กด/LOW) หรือ 1 (ปล่อย/HIGH)
- สัญญาณแอนะล็อก (Analog Input - ADC):
    * ESP32 มีความละเอียด 12-bit ค่าที่อ่านได้คือ 0 ถึง 4095
    * ต้องตั้งค่า adc.atten(ADC.ATTN_11V) เพื่อให้อ่านแรงดันได้เต็มช่วง 3.3V
    * สูตรคำนวณแรงดัน: Voltage = (ADC_Value * 3.3) / 4095
- การอ่านค่าเซนเซอร์เฉพาะ:
    * DHT22 (อุณหภูมิ/ความชื้น): ต้องใช้ library dht และต้องมีหน่วงเวลาอย่างน้อย 2 วินาทีระหว่างการอ่าน
    * LDR (เซนเซอร์แสง): เป็น Analog ต้องใช้ขาที่รองรับ ADC (เช่น ขา 32-39)

[ตัวอย่างการตอบคำถาม]
นักศึกษา: "อาจารย์ครับ ผมจะอ่านค่าจากปุ่มกดที่ขา 14 ต้องเขียนยังไง?"
ครูบอท: "สวัสดีครับ! การอ่านค่าปุ่มกดเราจะใช้สัญญาณดิจิทัลครับ 
ขั้นแรกเราต้องประกาศใช้ Pin จากโมดูล machine ก่อนนะ
ลองเริ่มพิมพ์แบบนี้ดูครับ:
1. import machine 
2. button = machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_UP)
ลองดูซิว่าถ้าใช้คำสั่ง print(button.value()) ตอนกดปุ่มกับไม่กดปุ่ม ค่าที่ได้ต่างกันยังไง?"
"""


def ask_typhoon(user_text):
    url = "https://api.opentyphoon.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {TYPHOON_API_KEY}"}
    payload = {
        "model": "typhoon-v2.5-30b-a3b-instruct",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.4,
        "max_tokens": 2048
        
    }
    res = requests.post(url, json=payload, headers=headers)
    result = res.json()
    if 'choices' not in result:
        print("--- Typhoon API Error Response ---")
        print(result) # ดูว่า AI ตอบกลับมาว่า Error เรื่องอะไร
        return "ขออภัยครับ ระบบประมวลผล AI ขัดข้อง"
    
    return result['choices'][0]['message']['content']

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # ดึงคำถามจาก LINE
    user_msg = event.message.text
    
    # ส่งไปถามไต้ฝุ่น
    ai_reply = ask_typhoon(user_msg)
    
    # ตอบกลับเข้า LINE
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=ai_reply)]
            )
        )

if __name__ == "__main__":
    app.run(port=5000)