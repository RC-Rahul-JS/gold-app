from flask import Blueprint, request, jsonify, current_app
from pymongo import MongoClient
from tvDatafeed import TvDatafeed, Interval
import jwt, pytz, json
from datetime import datetime, timedelta
import pytz
import random
import string
import requests
import razorpay, os
from zoneinfo import ZoneInfo

trade_bp = Blueprint('trade', __name__)
IST = pytz.timezone('Asia/Kolkata')

# ---- TradingView login ----
username = 'dssrgk7cm9'
password = 'Indu@2002#sep'
tv = TvDatafeed(username, password)




# ---- Helper Functions ----
def get_db():
    client = MongoClient(current_app.config['MONGO_URI'])
    return client['golddb']

def decode_token(token):
    try:
        decoded = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return decoded['user']
    except Exception:
        return None

def call_price(symbol):
    """Fetch live price from TradingView"""
    try:
        data = tv.get_hist(symbol=symbol, exchange='BINANCE', interval=Interval.in_1_minute, n_bars=1)
        data_json = json.loads(data.to_json())
        close_price = list(data_json['close'].values())[-1]
        return float(close_price/10)
    except Exception as e:
        print(f"Error fetching {symbol} price:", e)
        return 11230


# ---- BUY API ----
def buy(token,symbol,amount, razorpay_payment_id, razorpay_order_id):
    try:
        db = get_db()

        # --- Verify token ---
        if not token:
            return jsonify({'success': False, 'message': 'Token required'}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401

        user = db['users'].find_one({'phone_or_email': user_data})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        

        # --- Get current price from TradingView ---
        symbol_tv = f"{symbol}USDT"
        price = call_price(symbol_tv)
        if not price:
            return jsonify({'success': False, 'message': 'Failed to fetch live price'}), 500
        

        coinprice = price
        gstPercentege = 3
        priceInclusiveGst = round((amount*100)/(100+gstPercentege),2)

        coinGram = round(priceInclusiveGst/coinprice,4)

        sellAmount = priceInclusiveGst
        gst = round(amount-priceInclusiveGst,2)


        try:
            db = get_db()

            vouchers = db['vouchers']
            

            utc_now = datetime.now(ZoneInfo("UTC"))
            ist_now = utc_now.astimezone(ZoneInfo("Asia/Kolkata"))

                
            voucher_date = datetime.now(ZoneInfo("Asia/Kolkata"))
            date_str = voucher_date.strftime("%Y-%m-%d")
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            start = datetime(date_obj.year, date_obj.month, date_obj.day)
            end = start + timedelta(days=1)
            
    
            count_txn = vouchers.count_documents({})
            count = vouchers.count_documents({
                        "voucher_type": "Receipt",
                        "voucher_mode": "Bank",
                        "date": {"$gte": start, "$lt": end}   # between start and end of day
                    })
    
            voucher_number = "BRV-"+ str(date_str) +'-'+ str(count + 1)
            voucher = {
                        "amount":amount,
                        "voucher_number": voucher_number,
                        "voucher_type": 'Receipt',
                        "voucher_mode": "Bank",
                        "txn": count_txn + 1,
                        "user_id": user_data,
                        "symbol": symbol,
                        "to_id": razorpay_payment_id,
                        "date": datetime.now(ZoneInfo("Asia/Kolkata")),
                        "Payment_id": razorpay_payment_id,
                        "order_id": razorpay_order_id,
                        "narration": 'Buy '+symbol,
                        "entries": [
                    {
                    "narration": 'Buy '+symbol,
                    "ledger_id": "A6",
                    "ledger_name": "Razorpay",
                    "debit": amount,
                    "credit": 0
                    },
                    {
                    "narration": 'Buy '+symbol,
                    "ledger_id": "A3",
                    "ledger_name": "GST",
                    "debit": 0,
                    "credit": gst
                    },
                    {
                    "narration": 'Buy '+symbol,
                    "ledger_id": "A1",
                    "ledger_name": "Sales Account",
                    "debit": 0,
                    "credit": sellAmount
                    }
                    ],
                        "created_by": "system",
                        "created_at": ist_now
                    }
            vouchers.insert_one(voucher)
        except Exception as e:
            print("Error in /buy:", e)
            return jsonify({
            'success': False,
            'message': 'Server error occurred while processing buy order',
            'error': str(e)
            }), 500
    

        return jsonify({
            'success': True,
            'garm': coinGram,
            'amount':amount,
            'gst':gst,
            'sellAmount': sellAmount,

            # 'message': f'Bought {quantity} {symbol} @ {price}',
            'live_price': price
        }), 200

    except Exception as e:
        print("Error in /buy:", e)
        return jsonify({
            'success': False,
            'message': 'Server error occurred while processing buy order',
            'error': str(e)
        }), 500



def generate_order_id():
    # Current timestamp in YYYYMMDDHHMMSS format
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Random 4 letters (uppercase)
    letters = ''.join(random.choices(string.ascii_uppercase, k=4))
    
    # Combine
    order_id = f"COIN{timestamp}{letters}"
    return order_id

@trade_bp.route('/buy_request', methods=['POST'])
def buy_request():
    try:
        data = request.get_json(force=True)
        db = get_db()

        token = data.get('token')
        symbol = data.get('symbol', '').upper()
        amount = float(data.get('amount', 0))

        # --- Verify token ---
        if not token:
            return jsonify({'success': False, 'message': 'Token required'}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        

        orderId = generate_order_id()

        ist = pytz.timezone("Asia/Kolkata")
        current_time = datetime.now(ist)
        expire_time = current_time + timedelta(minutes=5)
        link_expire_by = expire_time.strftime("%d/%m/%Y %H:%M:%S")
        
        
        link_data = {
            "batchId": "batch1",
            "details": [
                {
                    "orderId": orderId,
                    "invoiceNumber": "INV9",
                    "amount": float(amount),
                    "internalNotes": "coin trade",
                    "linkExpireBy": link_expire_by,
                    "productDescription": "Buy "+ symbol,
                    "customerEmail": "gold@gmail.com",
                    "customerMobile": user_data,
                    "showQrImg":True,
                    "qrImgSize":{
                        "height":100,
                        "width":100
                    }
                }
            ]
        }

        url = "https://pay.zaakpay.com/pl/api/v1/create"

        headers = {
            "X-API-Key": "f307f09d771648f38925f8e8f7c593d4",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }


        res = requests.post(url, headers=headers, json=link_data)
        res.raise_for_status()
        response_data = res.json()
        url = response_data["data"][0]["link"]


        db['requests'].insert_one({
            'phone_or_email': user_data,
            'token':token,
            'symbol':symbol,
            'amount':amount,
            'orderId':orderId,
            'paymentLink':url,
            'created_at':current_time,
            'status':'created'
            })   

        return jsonify({
            'success': True,
            'link':url,
            'amount':amount
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Server error occurred while processing buy order',
            'error': str(e)
        }), 500


razorpay_client = razorpay.Client(auth=("rzp_test_RURrMWCkJodCsu", "XZJTq12WQYoE2yIPnnT34oEg"))

@trade_bp.route("/create_order", methods=["POST"])
def create_order():
    data = request.get_json()
    amount = float(data.get("amount", 0)) * 100  # in paise
    currency = "INR"
    token = data.get('token')

    if not token:
        return jsonify({'success': False, 'message': 'Token required'}), 401

    user_data = decode_token(token)
    if not user_data:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
    

    

    order = razorpay_client.order.create(dict(amount=amount, currency=currency, payment_capture=1))


    return jsonify(order)


def buy(token, symbol, amount, razorpay_payment_id, razorpay_order_id):
    try:
        db = get_db()

        if not token:
            return jsonify({'success': False, 'message': 'Token required'}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401

        user = db['users'].find_one({'phone_or_email': user_data})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # ---- Get current coin price ----
        symbol_tv = f"{symbol}USDT"
        price = call_price(symbol_tv)
        if not price:
            return jsonify({'success': False, 'message': 'Failed to fetch live price'}), 500

        # ---- Financial Calculations ----
        gstPercentege = 3
        priceInclusiveGst = round((amount * 100) / (100 + gstPercentege), 2)
        coinGram = round(priceInclusiveGst / price, 4)
        sellAmount = priceInclusiveGst
        gst = round(amount - priceInclusiveGst, 2)

        # ---- Voucher Entry ----
        vouchers = db['vouchers']
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
        date_str = ist_now.strftime("%Y-%m-%d")

        start = datetime(ist_now.year, ist_now.month, ist_now.day)
        end = start + timedelta(days=1)

        count_txn = vouchers.count_documents({})
        count = vouchers.count_documents({
            "voucher_type": "Receipt",
            "voucher_mode": "Bank",
            "date": {"$gte": start, "$lt": end}
        })

        voucher_number = f"BRV-{date_str}-{count + 1}"

        voucher = {
            "amount": amount,
            "voucher_number": voucher_number,
            "voucher_type": 'Receipt',
            "voucher_mode": "Bank",
            "txn": count_txn + 1,
            "user_id": user_data,
            "symbol": symbol,
            "to_id": razorpay_payment_id,
            "date": ist_now,
            "Payment_id": razorpay_payment_id,
            "order_id": razorpay_order_id,
            "narration": f'Buy {symbol}',
            "entries": [
                {"narration": f'Buy {symbol}', "ledger_id": "A6", "ledger_name": "Razorpay", "debit": amount, "credit": 0},
                {"narration": f'Buy {symbol}', "ledger_id": "A3", "ledger_name": "GST", "debit": 0, "credit": gst},
                {"narration": f'Buy {symbol}', "ledger_id": "A1", "ledger_name": "Sales Account", "debit": 0, "credit": sellAmount}
            ],
            "created_by": "system",
            "created_at": ist_now
        }

        transaction = {
            "amount": amount,
            "voucher_number": voucher_number,
            "voucher_type": 'Buy',
            "user_id": user_data,
            "symbol": symbol,
            "date": ist_now,
            "Payment_id": razorpay_payment_id,
            "order_id": razorpay_order_id,
            "created_by": "system",
            "created_at": ist_now,
            "amountGrams":coinGram,
            "gst":gst,
            "sellAmount":sellAmount
        }

        db['transaction'].insert_one(transaction)
        vouchers.insert_one(voucher)

        # ✅ Return Success
        return jsonify({
            "Payment_id": razorpay_payment_id,
            "created_at": ist_now,
            'success': True,
            'gram': coinGram,
            'amount': amount,
            'gst': gst,
            'sellAmount': sellAmount,
            'live_price': price
        }), 200

    except Exception as e:
        print("Error in /buy:", e)
        return jsonify({
            'success': False,
            'message': 'Server error occurred while processing buy order',
            'error': str(e)
        }), 500


# ✅ VERIFY PAYMENT ROUTE
@trade_bp.route("/verify_payment", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json(force=True)

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        token = data.get("token")
        symbol = data.get("symbol")
        amount = float(data.get("amount", 0))

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return jsonify({"success": False, "message": "Missing payment details"}), 400

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)

            db = get_db()

            # Prevent duplicate entries
            if db['vouchers'].find_one({'Payment_id': razorpay_payment_id}):
                return jsonify({
                    "success": False,
                    "message": "Duplicate payment detected"
                }), 409

            # Call buy() safely
            resp, code = buy(token, symbol, amount, razorpay_payment_id, razorpay_order_id)
            return resp, code

        except razorpay.errors.SignatureVerificationError:
            return jsonify({
                "success": False,
                "message": "Signature verification failed"
            }), 400

    except Exception as e:
        print("Error in verify_payment:", e)
        return jsonify({
            "success": False,
            "message": "Server error verifying payment",
            "error": str(e)
        }), 500
    




@trade_bp.route("/v1/vouchers", methods=["GET"])
def get_vouchers_filtered():
    from_date = request.args.get("from_date")  # e.g. 2025-08-01
    to_date = request.args.get("to_date")      # e.g. 2025-08-30
    voucher_type = request.args.get("voucher_type")  # optional
    voucher_mode = request.args.get("voucher_mode")  # optional
    
    db = get_db()
    vouchers = db['vouchers']
    # Convert string → datetime
    query = {}
    if from_date and to_date:
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
        # include till end of "to_date"
        end = datetime(end.year, end.month, end.day, 23, 59, 59)
        query["date"] = {"$gte": start, "$lte": end}
    
    if voucher_type:
        query["voucher_type"] = voucher_type

    if voucher_mode:
        query["voucher_mode"] = voucher_mode
    
    
    # Fetch vouchers
    vouchers_list = list(vouchers.find(query))
    
    # Convert ObjectId to str
    for v in vouchers_list:
        v["_id"] = str(v["_id"])
    
    return jsonify(vouchers_list)


@trade_bp.route('/v1/ledger/<ledger_id>', methods=['GET'])
def get_ledger_entries(ledger_id):
    # query params: ?from=2025-08-01&to=2025-08-30
    from_date_str = request.args.get("from")
    to_date_str = request.args.get("to")

    db = get_db()
    vouchers = db['vouchers']

    try:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None
    except Exception:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400

    # Opening balance = all entries before from_date
    opening_balance = 0
    if from_date:
        before_cursor = vouchers.find({"entries.ledger_id": ledger_id, "date": {"$lt": from_date}})
        for doc in before_cursor:
            for entry in doc.get("entries", []):
                if entry.get("ledger_id") == ledger_id:
                    opening_balance += (entry.get("debit", 0) - entry.get("credit", 0))

    # Current period transactions
    query = {"entries.ledger_id": ledger_id}
    if from_date and to_date:
        query["date"] = {"$gte": from_date, "$lte": to_date}
    elif from_date:
        query["date"] = {"$gte": from_date}
    elif to_date:
        query["date"] = {"$lte": to_date}


    results = vouchers.find(query)

    ledger_entries = []
    for doc in results:
        for entry in doc.get("entries", []):
            if entry.get("ledger_id") == ledger_id:
                ledger_entries.append({
                    "voucher_number": doc.get("voucher_number"),
                    "voucher_type": doc.get("voucher_type"),
                    "voucher_mode": doc.get("voucher_mode"),
                    "txn": doc.get("txn"),
                    "ledger_id": entry.get("ledger_id"),
                    "ledger_name": entry.get("ledger_name"),
                    "credit": entry.get("credit"),
                    "debit": entry.get("debit"),
                    "narration": entry.get("narration"),
                    "date": doc.get("date"),
                })

    ledger_entries.sort(key=lambda x: x["date"])

    return jsonify({
        "ledger_id": ledger_id,
        "opening_balance": opening_balance,
        "transaction_count": len(ledger_entries),
        "transactions": ledger_entries
    })



# ---------- Route ----------
@trade_bp.route("/get_transactions", methods=["POST"])
def get_transactions():
    try:
        db = get_db()
        data = request.get_json()

        token = data.get("token")
        if not token:
            return jsonify({"success": False, "message": "Token required"}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({"success": False, "message": "Invalid or expired token"}), 401

        # Fetch transactions for the user
        transactions = list(
            db['transaction'].find(
                {"user_id": user_data},
                {"_id": 0}  # Hide MongoDB _id
            ).sort("date", -1)
        )

        if not transactions:
            return jsonify({
                "success": True,
                "message": "No transactions found",
                "transactions": []
            }), 200

        # Format for frontend readability
        for txn in transactions:
            txn['date'] = txn['date'].astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            "success": True,
            "count": len(transactions),
            "transactions": transactions
        }), 200

    except Exception as e:
        print("Error in /get_transactions:", e)
        return jsonify({
            "success": False,
            "message": "Server error fetching transactions",
            "error": str(e)
        }), 500
    
@trade_bp.route("/get_transactions_by_symbol", methods=["POST"])
def get_transactions_by_coin():
    try:
        db = get_db()
        data = request.get_json()

        token = data.get("token")
        symbol = data.get("symbol")
        if not token:
            return jsonify({"success": False, "message": "Token required"}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({"success": False, "message": "Invalid or expired token"}), 401

        # Fetch transactions for the user
        transactions = list(
            db['transaction'].find(
                {"user_id": user_data, "symbol":symbol},
                {"_id": 0}  # Hide MongoDB _id
            ).sort("date", -1)
        )

        if not transactions:
            return jsonify({
                "success": True,
                "message": "No transactions found",
                "transactions": []
            }), 200

        # Format for frontend readability
        for txn in transactions:
            txn['date'] = txn['date'].astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")

        total = 0.0
        total_grams = 0.0

        for item in transactions:
            amount = float(item["sellAmount"])
            grams = float(item["amountGrams"])
            if item["voucher_type"] == "Buy":
                total += amount
                total_grams += grams
            elif item["voucher_type"] == "Sell":
                total -= amount
                total_grams -= grams

        return jsonify({
            "success": True,
            "count": len(transactions),
            "transactions": transactions,
            "balance": round(total, 2),
            "total_gram": round(total_grams, 4),
        }), 200

    except Exception as e:
        print("Error in /get_transactions:", e)
        return jsonify({
            "success": False,
            "message": "Server error fetching transactions",
            "error": str(e)
        }), 500




def sell(token, symbol, amount, razorpay_payment_id, razorpay_order_id):
    try:
        db = get_db()

        if not token:
            return jsonify({'success': False, 'message': 'Token required'}), 401

        user_data = decode_token(token)
        if not user_data:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401

        user = db['users'].find_one({'phone_or_email': user_data})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # ---- Get current coin price ----
        symbol_tv = f"{symbol}USDT"
        price = call_price(symbol_tv)
        if not price:
            return jsonify({'success': False, 'message': 'Failed to fetch live price'}), 500

        # ---- Financial Calculations ----
        gstPercentege = 3
        priceInclusiveGst = round((amount * 100) / (100 + gstPercentege), 2)
        coinGram = round(priceInclusiveGst / price, 4)
        sellAmount = priceInclusiveGst
        gst = round(amount - priceInclusiveGst, 2)

        # ---- Voucher Entry ----
        vouchers = db['vouchers']
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
        date_str = ist_now.strftime("%Y-%m-%d")

        start = datetime(ist_now.year, ist_now.month, ist_now.day)
        end = start + timedelta(days=1)

        count_txn = vouchers.count_documents({})
        count = vouchers.count_documents({
            "voucher_type": "Payment",
            "voucher_mode": "Bank",
            "date": {"$gte": start, "$lt": end}
        })

        voucher_number = f"BRV-{date_str}-{count + 1}"

        voucher = {
            "amount": amount,
            "voucher_number": voucher_number,
            "voucher_type": 'Payment',
            "voucher_mode": "Bank",
            "txn": count_txn + 1,
            "user_id": user_data,
            "symbol": symbol,
            "to_id": razorpay_payment_id,
            "date": ist_now,
            "Payment_id": razorpay_payment_id,
            "order_id": razorpay_order_id,
            "narration": f'Sell {symbol}',
            "entries": [
                {"narration": f'Sell {symbol}', "ledger_id": "A6", "ledger_name": "Razorpay", "debit": 0, "credit": amount},
                {"narration": f'Sell {symbol}', "ledger_id": "A5", "ledger_name": "RCM", "debit": gst, "credit": 0},
                {"narration": f'Sell {symbol}', "ledger_id": "A4", "ledger_name": "Purchase Account", "debit": sellAmount, "credit": 0}
            ],
            "created_by": "system",
            "created_at": ist_now
        }

        transaction = {
            "amount": amount,
            "voucher_number": voucher_number,
            "voucher_type": 'Sell',
            "user_id": user_data,
            "symbol": symbol,
            "date": ist_now,
            "Payment_id": razorpay_payment_id,
            "order_id": razorpay_order_id,
            "created_by": "system",
            "created_at": ist_now,
            "amountGrams":coinGram,
            "gst":gst,
            "sellAmount":sellAmount
        }

        db['transaction'].insert_one(transaction)
        vouchers.insert_one(voucher)

        # ✅ Return Success
        return jsonify({
            "Payment_id": razorpay_payment_id,
            "created_at": ist_now,
            'success': True,
            'gram': coinGram,
            'amount': amount,
            'gst': gst,
            'sellAmount': sellAmount,
            'live_price': price
        }), 200

    except Exception as e:
        print("Error in /buy:", e)
        return jsonify({
            'success': False,
            'message': 'Server error occurred while processing buy order',
            'error': str(e)
        }), 500


# ✅ VERIFY PAYMENT ROUTE
@trade_bp.route("/sell", methods=["POST"])
def sellcoin():
    try:
        data = request.get_json(force=True)

        razorpay_order_id = generate_order_id()
        razorpay_payment_id = generate_order_id()
        token = data.get("token")
        symbol = data.get("symbol")
        amount = float(data.get("amount", 0))

        if not all([token, symbol, amount]):
            return jsonify({"success": False, "message": "Missing payment details"}), 400

        try:

            db = get_db()

            # Prevent duplicate entries
            if db['vouchers'].find_one({'Payment_id': razorpay_payment_id}):
                return jsonify({
                    "success": False,
                    "message": "Duplicate payment detected"
                }), 409

            # Call buy() safely
            resp, code = sell(token, symbol, amount, razorpay_payment_id, razorpay_order_id)
            return resp, code

        except:
            return jsonify({
                "success": False,
                "message": "Signature verification failed"
            }), 400

    except Exception as e:
        print("Error in verify_payment:", e)
        return jsonify({
            "success": False,
            "message": "Server error verifying payment",
            "error": str(e)
        }), 500
    
