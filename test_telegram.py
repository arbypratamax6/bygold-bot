import os
import requests
from dotenv import load_dotenv

# Baca file .env
load_dotenv("env.env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text):
    """Kirim pesan ke Telegram untuk tes koneksi"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, data=payload)
    print(r.status_code, r.text)

# Tes kirim pesan
send_telegram_message("✅ Tes koneksi berhasil! Bot kamu sudah bisa kirim pesan 🚀")
