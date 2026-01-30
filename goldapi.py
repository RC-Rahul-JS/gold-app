from tvDatafeed import TvDatafeed, Interval
import json
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import pytz

price_bp = Blueprint("coin", __name__)

# ---- Login once ----
username = 'dssrgk7cm9'
password = 'Indu@2002#sep'
tv = TvDatafeed(username, password)


# ---- Helper Function ----
def call(symbol):
    try:
        data = tv.get_hist(
            symbol=symbol,
            exchange='BINANCE',
            interval=Interval.in_1_minute,
            n_bars=1
        )
        return json.loads(data.to_json())
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None


# ---- Flask Route ----
@price_bp.route("/getprice", methods=["GET"])
def getpriceapi():
    gold_data = call('BTCUSDT')
    silver_data = call('ETHUSDT')

    # Error handling
    if not gold_data or not silver_data:
        return jsonify({'error': 'Failed to fetch data'}), 500

    try:
        # ---- Extract Close Values ----
        close_gold = list(gold_data['close'].values())[-1]
        close_silver = list(silver_data['close'].values())[-1]
        
        open_gold = list(gold_data['open'].values())[-1]
        open_silver = list(silver_data['open'].values())[-1]

        # ---- India Time + 5 mins ----
        india = pytz.timezone('Asia/Kolkata')
        now = datetime.now(india)
        future_time = now + timedelta(minutes=5)

        # ---- Prepare Response ----
        response = {
            'Expiry': future_time.strftime("%Y-%m-%d %H:%M:%S"),
            'Gold': round(close_gold / 10, 2),
            'Silver': round(close_silver / 10, 2),
            'Sell_Gold': round(open_gold / 10, 2),
            'Sell_Silver': round(open_silver / 10, 2),
        }
        return jsonify(response)

    except Exception as e:
        print("Error processing data:", e)
        return jsonify({'error': 'Processing error'}), 500
    
