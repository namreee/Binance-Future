# === TAM STRATEJI BOTU – 1. PARÇA ===

# 📦 GEREKEN MODÜLLER:
# pip install python-binance flask python-dotenv pandas

import time
import threading
import logging
from flask import Flask, request
from binance.client import Client
from binance.exceptions import BinanceAPIException
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
import pandas as pd
import os

# === ENV VARIABLES ===
load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

# === INIT ===
client = Client(API_KEY, API_SECRET)
app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(threadName)s — %(message)s"
)
logger = logging.getLogger(__name__)
symbol_locks = {}

# === STATIC PRECISION TABLES ===
quantity_precision_table = {
    "BTCUSDT": 3, "ETHUSDT": 3, "SANDUSDT": 0, "GOATUSDT": 0, "WLDUSDT": 0,
    "RONINUSDT": 0, "IMXUSDT": 0, "COOKIEUSDT": 0, "GRIFFAINUSDT": 0,
    "PIXELUSDT": 0, "PENGUUSDT": 0, "PYTHUSDT": 0, "NEARUSDT": 0,
    "NEIROUSDT": 0, "CAKEUSDT": 0, "STXUSDT": 0, "HBARUSDT": 0,
    "AI16ZUSDT": 0, "BERAUSDT": 0, "PNUTUSDT": 0, "RSRUSDT": 0,
    "SUSDT": 0, "VIRTUALUSDT": 0, "XLMUSDT": 0, "XAIUSDT": 0,
    "DEGENUSDT": 0, "TIAUSDT": 0, "1000BONKUSDT": 0, "AIXBTUSDT": 0
}

price_precision_table = {
    "BTCUSDT": 2, "ETHUSDT": 2, "SANDUSDT": 4, "GOATUSDT": 4, "WLDUSDT": 4,
    "RONINUSDT": 4, "IMXUSDT": 4, "COOKIEUSDT": 4, "GRIFFAINUSDT": 4,
    "PIXELUSDT": 4, "PENGUUSDT": 4, "PYTHUSDT": 4, "NEARUSDT": 4,
    "NEIROUSDT": 4, "CAKEUSDT": 4, "STXUSDT": 4, "HBARUSDT": 4,
    "AI16ZUSDT": 4, "BERAUSDT": 4, "PNUTUSDT": 4, "RSRUSDT": 4,
    "SUSDT": 4, "VIRTUALUSDT": 4, "XLMUSDT": 4, "XAIUSDT": 4,
    "DEGENUSDT": 4, "TIAUSDT": 4, "1000BONKUSDT": 8, "AIXBTUSDT": 4
}

logger.info("✅ Precision tabloları yüklendi.")

# === FORMATLAYICI FONKSİYONLAR ===

def format_quantity(symbol, quantity):
    precision = quantity_precision_table.get(symbol, 0)
    factor = Decimal(10) ** precision
    formatted = Decimal(quantity).quantize(Decimal(1) / factor, rounding=ROUND_DOWN)
    formatted_float = float(formatted)
    if formatted_float <= 0:
        logger.warning(f"⚠️ {symbol} için formatlanan miktar 0 veya negatif! 1.0 olarak düzeltildi.")
        return 1.0
    return formatted_float

def format_price(symbol, price):
    precision = price_precision_table.get(symbol, 4)
    factor = Decimal(10) ** precision
    formatted = Decimal(price).quantize(Decimal(1) / factor, rounding=ROUND_DOWN)
    return float(formatted)

# === EMA200 HESAPLAMA ===

def get_ema200(symbol, timeframe):
    interval_map = {
        "15m": "2h", "30m": "4h", "1h": "4h", "2h": "8h", "4h": "12h"
    }
    ema_interval = interval_map.get(timeframe, "4h")
    try:
        klines = client.futures_klines(symbol=symbol, interval=ema_interval, limit=200)
        closes = [float(k[4]) for k in klines]
        df = pd.DataFrame(closes, columns=["close"])
        ema = df["close"].ewm(span=200, adjust=False).mean().iloc[-1]
        logger.info(f"📈 {symbol} için EMA200 ({ema_interval}) hesaplandı: {ema}")
        return ema
    except Exception as e:
        logger.warning(f"⚠️ {symbol} EMA hesaplama hatası: {e}")
        return None

# === USDT MİKTARI HESAPLAMA ===

def get_usdt_amount(symbol, timeframe, signal_type, price, ema200):
    above = price > ema200
    table = {
        "15m": (300, 600),
        "30m": (400, 800),
        "1h":  (500, 1000),
        "2h":  (500, 1600),
        "4h":  (500, 2000)
    }
    low, high = table.get(timeframe, (300, 600))
    amount = high if (signal_type == "LONG" and above) or (signal_type == "SHORT" and not above) else low
    logger.info(f"💰 {symbol} için kullanılacak USDT miktarı: {amount} ({'yüksek' if amount == high else 'düşük'} risk)")
    return amount
def cancel_all_open_orders(symbol):
    try:
        client.futures_cancel_all_open_orders(symbol=symbol)
        logger.info(f"🔁 {symbol} için tüm açık emirler iptal edildi.")
    except Exception as e:
        logger.warning(f"⚠️ {symbol} emir iptal hatası: {e}")

def close_position_if_open(symbol):
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            amt = float(pos["positionAmt"])
            if amt != 0:
                side = "SELL" if amt > 0 else "BUY"
                qty = abs(amt)
                logger.info(f"🔄 {symbol} açık pozisyon kapatılıyor → {side}, qty={qty}")
                place_market_order(symbol, side, qty)
                cancel_all_open_orders(symbol)
    except Exception as e:
        logger.warning(f"❗ {symbol} pozisyon kapatma hatası: {e}")

def place_market_order(symbol, side, quantity, reduce_only=False):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
            reduceOnly=reduce_only
        )
        executed = float(order.get("executedQty", 0))
        if executed == 0:
            # Pozisyonu manuel kontrol et
            pos_info = client.futures_position_information(symbol=symbol)
            for p in pos_info:
                if p["symbol"] == symbol:
                    pos_amt = float(p["positionAmt"])
                    if (side == "BUY" and pos_amt > 0) or (side == "SELL" and pos_amt < 0):
                        logger.warning(f"⚠️ Market emri görünmüyor ama pozisyon açılmış: {pos_amt}")
                        return abs(pos_amt)
            logger.error(f"❌ {symbol} market emri başarısız (executedQty=0)")
            return 0
        logger.info(f"📥 Market emri başarıyla işlendi: {executed} {side}, reduceOnly={reduce_only}")
        return executed
    except BinanceAPIException as e:
        logger.error(f"❌ {symbol} market emri hatası: {e}")
        return 0

def place_stop_loss(symbol, side, entry_price_1, entry_price_2):
    """
    Ortalama girişin %3.5 uzağına STOP_MARKET emri koyar.
    Miktar: Gerçek pozisyonun %60'ı.
    """
    avg_entry_price = (entry_price_1 * 0.4 + entry_price_2 * 0.6)

    if side == "BUY":
        sl_price = avg_entry_price * 0.965
        stop_side = "SELL"
    else:
        sl_price = avg_entry_price * 1.035
        stop_side = "BUY"

    sl_price = format_price(symbol, sl_price)

    # 🔍 Binance'ten açık pozisyonu al
    try:
        positions = client.futures_position_information(symbol=symbol)
        for p in positions:
            if p["symbol"] == symbol:
                position_amt = abs(float(p["positionAmt"]))
                break
        else:
            logger.warning(f"⚠️ SL için {symbol} pozisyon bilgisi bulunamadı.")
            return
    except Exception as e:
        logger.error(f"❌ SL için pozisyon bilgisi alınamadı: {e}")
        return

    sl_qty = format_quantity(symbol, position_amt * 0.6)

    try:
        client.futures_create_order(
            symbol=symbol,
            side=stop_side,
            type="STOP_MARKET",
            stopPrice=sl_price,
            quantity=sl_qty,
            timeInForce="GTC",
            reduceOnly=True
        )
        logger.info(f"🛑 STOP-LOSS kondu → fiyat: {sl_price}, miktar: {sl_qty} (%60 pozisyon), yön: {stop_side}")
    except Exception as e:
        logger.error(f"❌ STOP-LOSS gönderilemedi: {e}")


def place_take_profit(symbol, side, entry_price_60, qty_40):
    tp_price = entry_price_60 * 1.08 if side == "BUY" else entry_price_60 * 0.92
    tp_price = format_price(symbol, tp_price)
    try:
        client.futures_create_order(
            symbol=symbol,
            side="SELL" if side == "BUY" else "BUY",
            type="LIMIT",
            price=tp_price,
            quantity=qty_40,
            timeInForce="GTC",
            reduceOnly=True
        )
        logger.info(f"🎯 TP kondu → fiyat: {tp_price} (%8 yukarı), sadece %40 reduceOnly")
    except Exception as e:
        logger.error(f"❌ TP gönderilemedi: {e}")
def get_rsi(symbol, interval="1m", period=14):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=period + 1)
        closes = [float(k[4]) for k in klines]
        delta = pd.Series(closes).diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"⚠️ RSI hesaplama hatası: {e}")
        return 50

def handle_trade(symbol, action, leverage, timeframe):
    if symbol_locks.get(symbol, False):
        logger.warning(f"⛔ {symbol} zaten kilitli. İşlem atlandı.")
        return
    symbol_locks[symbol] = True

    try:
        side = "BUY" if action == "LONG" else "SELL"
        close_position_if_open(symbol)
        time.sleep(1)
        cancel_all_open_orders(symbol)

        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        try:
            client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
        except BinanceAPIException as e:
            if "No need to change margin type" not in str(e):
                logger.warning(f"⚠️ {symbol} margin tipi ayarlanamadı: {e}")

        price = float(client.futures_mark_price(symbol=symbol)["markPrice"])
        ema = get_ema200(symbol, timeframe)
        if ema is None:
            logger.error(f"❌ {symbol} için EMA alınamadı.")
            return

        usdt_amount = get_usdt_amount(timeframe, action, price, ema)
        qty_total = usdt_amount / price
        qty_20 = format_quantity(symbol, qty_total * 0.2)
        qty_40 = format_quantity(symbol, qty_total * 0.4)

        exec_qty_20 = place_market_order(symbol, side, qty_20)
        if exec_qty_20 == 0:
            return
        logger.info(f"✅ {symbol} için %20 alım yapıldı — fiyat: {price}")
        entry_price = price

        wait_map = {"15m": (45, 75, 105, 135), "30m": (90, 150, 210, 270), "1h": (180, 300, 420, 540)}
        t3, t5, t7, t9 = wait_map.get(timeframe, (45, 75, 105, 135))

        second_entry_price = None
        third_entry_price = None
        exec_qty_40_2 = 0
        exec_qty_40_3 = 0

        for delay in [t3, t5]:
            time.sleep(delay if delay == t3 else t5 - t3)
            price_now = float(client.futures_mark_price(symbol=symbol)["markPrice"])
            klines = client.futures_klines(symbol=symbol, interval="1m", limit=21)
            vol_3 = sum(float(k[5]) for k in klines[-4:-1])
            vol_20 = sum(float(k[5]) for k in klines[:-1]) / 20
            if price_now > entry_price and vol_3 > vol_20:
                exec_qty_40_2 = place_market_order(symbol, side, qty_40)
                if exec_qty_40_2 > 0:
                    second_entry_price = price_now
                    logger.info(f"✅ {symbol} için %40 2. alım yapıldı — fiyat: {price_now}")
                    avg_price = (entry_price * exec_qty_20 + second_entry_price * exec_qty_40_2) / (exec_qty_20 + exec_qty_40_2)
                    sl_price = format_price(symbol, avg_price * 0.97)
                    sl_qty = format_quantity(symbol, (exec_qty_20 + exec_qty_40_2) * 0.6)
                    sl_side = "SELL" if side == "BUY" else "BUY"
                    client.futures_create_order(symbol=symbol, side=sl_side, type="STOP_MARKET",
                                                stopPrice=sl_price, quantity=sl_qty,
                                                timeInForce="GTC")
                    logger.info(f"🛑 SL kondu: {sl_price} — qty: {sl_qty}")
                    break
        # === 3. Alım Denemeleri (5., 7., 9. barlarda RSI kontrolü) ===
        if second_entry_price:
            for delay in [t5, t7, t9]:
                time.sleep(t7 - t5 if delay == t7 else (t9 - t7 if delay == t9 else 0))
                price_now = float(client.futures_mark_price(symbol=symbol)["markPrice"])
                rsi_now = get_rsi(symbol)
                if price_now > second_entry_price and rsi_now > 58:
                    exec_qty_40_3 = place_market_order(symbol, side, qty_40)
                    if exec_qty_40_3 > 0:
                        third_entry_price = price_now
                        logger.info(f"✅ {symbol} için %40 3. alım yapıldı — fiyat: {price_now}")
                        # === TAKE-PROFIT (%8 yukarıya, toplam qty'nin %40'ı) ===
                        tp_price = format_price(symbol, third_entry_price * 1.08)
                        total_qty = exec_qty_20 + exec_qty_40_2 + exec_qty_40_3
                        tp_qty = format_quantity(symbol, total_qty * 0.4)
                        tp_side = "SELL" if side == "BUY" else "BUY"
                        client.futures_create_order(symbol=symbol, side=tp_side, type="LIMIT",
                                                    price=tp_price, quantity=tp_qty,
                                                    reduceOnly=True, timeInForce="GTC")
                        logger.info(f"🎯 TP kondu → fiyat: {tp_price}, miktar: {tp_qty}")
                        break

    except Exception as e:
        logger.error(f"❌ {symbol} işlem hatası: {e}")
    finally:
        symbol_locks[symbol] = False
        logger.info(f"🔓 {symbol} kilit açıldı. İşlem tamamlandı.")

# === FLASK ROUTES ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logger.info(f"📩 Webhook alındı: {data}")
    if data.get("auth") != AUTH_TOKEN:
        return "Unauthorized", 401
    symbol = data["symbol"]
    action = data["action"]
    leverage = int(data.get("leverage", 10))
    timeframe = data.get("timeframe", "15m")
    threading.Thread(
        target=handle_trade,
        args=(symbol, action, leverage, timeframe),
        name=f"{symbol}-Worker"
    ).start()
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Binance Futures Bot Aktif"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
