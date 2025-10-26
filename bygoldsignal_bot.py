import os
import datetime as dt
import yfinance as yf
import pandas as pd
import requests
from dotenv import load_dotenv
import time

load_dotenv("env.env")

# ===== KONFIGURASI =====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TICKER = os.getenv("GOLD_TICKER", "GC=F")  # default gold futures (aktif)
# ========================


def send_telegram_message(text):
    """Kirim pesan ke Telegram (dengan debug)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}

    print(f"\n[DEBUG] Mengirim ke Telegram...")
    print(f"URL  : {url}")
    print(f"CHAT : {CHAT_ID}")
    print(f"TEXT : {text}\n")

    try:
        response = requests.post(url, data=payload, timeout=15)
        print(f"[DEBUG] Response dari Telegram → {response.status_code}: {response.text}\n")
    except Exception as e:
        print(f"[DEBUG] Telegram error: {e}\n")



def get_data(ticker, period, interval):
    """Ambil data dari Yahoo Finance (kompatibel semua versi)"""
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        threads=False,
        auto_adjust=False,
    )

    if df is None or df.empty:
        print(f"⚠️ Tidak ada data untuk {ticker} (interval={interval}, period={period})")
        return None

    # ✅ Jika MultiIndex: gunakan level 1 (nama kolom sebenarnya)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[1] if len(col) > 1 else col[0] for col in df.columns]

    # ✅ Jika masih berbentuk satu kolom berulang (seperti ['GC=F', ...]), periksa level header
    if all(col == ticker for col in df.columns):
        try:
            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                threads=False,
                auto_adjust=False,
                group_by="ticker",
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(1)
        except Exception as e:
            print(f"⚠️ Gagal memperbaiki struktur kolom: {e}")

    # ✅ Normalisasi nama kolom
    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adjclose": "Close",
        "adj close": "Close",
    }
    df.columns = [rename_map.get(col.lower(), col) for col in df.columns]

    if "Close" not in df.columns:
        print(f"❌ Kolom 'Close' tidak ditemukan. Kolom tersedia: {list(df.columns)}")
        return None

    df.dropna(inplace=True)
    return df


def ema(df, period):
    """Hitung EMA dengan aman"""
    close_col = df["Close"]
    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.iloc[:, 0]
    return close_col.ewm(span=period, adjust=False).mean()


def analyze_and_alert():
    # 1️⃣ Tren utama di H1
    df_h1 = get_data(TICKER, period="30d", interval="1h")
    if df_h1 is None:
        print("❌ Gagal ambil data, keluar.")
        return

    df_h1["EMA21"] = ema(df_h1, 21)
    df_h1["EMA34"] = ema(df_h1, 34)
    df_h1["EMA90"] = ema(df_h1, 90)

    ema21 = df_h1["EMA21"].iloc[-1]
    ema34 = df_h1["EMA34"].iloc[-1]
    ema90 = df_h1["EMA90"].iloc[-1]

    if ema21 > ema34 and ema34 > ema90:
        trend = "BUY"
    elif ema21 < ema34 and ema34 < ema90:
        trend = "SELL"
    else:
        trend = None

    if not trend:
        print("❎ Tidak ada tren jelas di H1, tidak kirim sinyal.")
        return

    # 2️⃣ Cek retest di TF kecil
    def check_retest(tf_label, interval):
        df = get_data(TICKER, period="3d", interval=interval)
        if df is None:
            return None

        df["EMA21"] = ema(df, 21)
        df["EMA34"] = ema(df, 34)

        def get_last_value(series_or_df):
            if isinstance(series_or_df, pd.DataFrame):
                return float(series_or_df.iloc[-1, 0])
            return float(series_or_df.iloc[-1])

        price = get_last_value(df["Close"])
        ema21_last = get_last_value(df["EMA21"])
        ema34_last = get_last_value(df["EMA34"])

        lower = min(ema21_last, ema34_last)
        upper = max(ema21_last, ema34_last)

        # 🔸 Tambahan logika "ALMOST RETEST"
        margin = 0.001  # 0.1% toleransi
        distance_to_ema = min(abs(price - lower), abs(price - upper))

        if lower <= price <= upper:
            return f"⚠ <b>WARNING {trend}</b> – harga retest area EMA21–34 di TF {tf_label} (price: {price:.2f})"
        elif distance_to_ema / price <= margin:
            return f"🔸 <b>ALMOST RETEST {trend}</b> – harga mendekati area EMA21–34 di TF {tf_label} (price: {price:.2f})"
        return None

    warnings = []
    for tf, label in [("5m", "5m"), ("15m", "15m")]:
        msg = check_retest(label, tf)
        if msg:
            warnings.append(msg)

    # 3️⃣ Kirim hanya jika ada retest
    if warnings:
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_info = (
            f"📊 <b>GOLD EMA Retest Alert</b>\n"
            f"⏰ {now}\n"
            f"Symbol: {TICKER}\n"
            f"Timeframe: H1\n"
            f"Trend: <b>{trend}</b>\n"
            f"EMA21: {ema21:.2f} | EMA34: {ema34:.2f} | EMA90: {ema90:.2f}\n"
        )
        text = base_info + "\n".join(warnings)
        send_telegram_message(text)
        print(text)
    else:
        print("✅ Tidak ada retest, tidak kirim sinyal.")

# 🔁 Jalankan tes + loop otomatis
if __name__ == "__main__":
    # 🔹 Tes kirim pesan dulu
    test_text = "✅ Tes koneksi berhasil! Bot sudah bisa mengirim ke Telegram."
    print("Mengirim pesan tes ke Telegram...")
    send_telegram_message(test_text)
    print("Pesan tes dikirim ke Telegram.\n")

    # 🔹 Lanjut ke loop utama
    while True:
        analyze_and_alert()
        print("⏳ Tunggu 2 menit sebelum cek ulang...\n")
        time.sleep(120)



