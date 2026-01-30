from flask import Blueprint, request, jsonify, current_app
from pymongo import MongoClient
import random, time, jwt, requests, pytz
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)
IST = pytz.timezone('Asia/Kolkata')

# ---------------- Helper Functions ----------------
def get_db():
    client = MongoClient(current_app.config['MONGO_URI'])
    return client['golddb']

def generate_otp():
    return str(random.randint(1000, 9999))

def send_otp(phone_or_email, otp):
    try:
        EXTERNAL_API_URL = f"https://www.fast2sms.com/dev/bulkV2?authorization={current_app.config['FAST2SMS_API_KEY']}&route=dlt&sender_id=LCLPRI&message=185893&variables_values={otp}%7C&numbers={phone_or_email}"
        response = requests.get(EXTERNAL_API_URL, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        print("OTP Send Error:", e)
        return False

def is_token_blacklisted(token):
    db = get_db()
    return db['blacklisted_tokens'].find_one({'token': token}) is not None

# ------------------- Routes ----------------------
@auth_bp.route('/send_otp', methods=['POST'])
def send_otp_api():
    db = get_db()
    otp_col = db['otp_requests']

    data = request.get_json()
    phone_or_email = data.get('phone_or_email')

    if not phone_or_email:
        return jsonify({'success': False, 'message': 'Phone or email required'}), 400

    otp = generate_otp()
    if not send_otp(phone_or_email, otp):
        return jsonify({'success': False, 'message': 'Failed to send OTP'}), 500

    otp_record = {
        'phone_or_email': phone_or_email,
        'otp': otp,
        'timestamp': time.time(),
        'created_at': datetime.now(IST)
    }

    otp_col.update_one({'phone_or_email': phone_or_email}, {'$set': otp_record}, upsert=True)
    return jsonify({'success': True, 'message': 'OTP sent successfully'})

@auth_bp.route('/verify_otp', methods=['POST'])
def verify_otp_api():
    db = get_db()
    otp_col = db['otp_requests']
    users_col = db['users']

    data = request.get_json()
    phone_or_email = data.get('phone_or_email')
    user_otp = data.get('otp')

    if not phone_or_email or not user_otp:
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    record = otp_col.find_one({'phone_or_email': phone_or_email})
    if not record:
        return jsonify({'success': False, 'message': 'OTP not found. Please request again'}), 400

    if time.time() - record['timestamp'] > 300:
        return jsonify({'success': False, 'message': 'OTP expired'}), 400

    if record['otp'] != user_otp:
        return jsonify({'success': False, 'message': 'Invalid OTP'}), 400

    user = users_col.find_one({'phone_or_email': phone_or_email})
    if not user:
        users_col.insert_one({'phone_or_email': phone_or_email, 'created_at': datetime.now(IST)})

    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(days=180)  # 6 months token validity

    token = jwt.encode(
        {'user': phone_or_email, 'iat': issued_at.timestamp(), 'exp': expires_at.timestamp()},
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    otp_col.delete_one({'phone_or_email': phone_or_email})

    return jsonify({'success': True, 'message': 'OTP verified successfully', 'token': token})

@auth_bp.route('/verify_token', methods=['POST'])
def verify_token():
    data = request.get_json()
    token = data.get('token')

    if is_token_blacklisted(token):
        return jsonify({'success': False, 'message': 'Token blacklisted'}), 401

    try:
        decoded = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return jsonify({'success': True, 'user': decoded['user']})
    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Token expired'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': 'Invalid token', 'error': str(e)}), 400

@auth_bp.route('/logout', methods=['POST'])
def logout():
    db = get_db()
    blacklist_col = db['blacklisted_tokens']

    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({'success': False, 'message': 'Token required'}), 400

    try:
        decoded = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        blacklist_col.insert_one({
            'token': token,
            'user': decoded['user'],
            'blacklisted_at': datetime.now(IST)
        })
        return jsonify({'success': True, 'message': 'Logged out successfully'})
    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Token already expired'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Invalid token', 'error': str(e)}), 400


@auth_bp.route('/update_profile', methods=['POST'])
def update_profile():
    data = request.get_json()
    token = data.get('token')
    name = data.get('name')
    nominee = data.get('nominee')
    address = data.get('address')

    if not token:
        return jsonify({'success': False, 'message': 'Token missing'}), 401

    try:
        # Decode token
        decoded = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        phone_or_email = decoded['user']

        # Update user info
        update_data = {
            'updated_at': datetime.now(IST)
        }

        if name:
            update_data['name'] = name
        if nominee:
            update_data['nominee'] = nominee
        if address:
            update_data['address'] = address

        db = get_db()
        users_col = db['users']

        result = users_col.update_one(
            {'phone_or_email': phone_or_email},
            {'$set': update_data}
        )

        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Profile updated successfully'})
        else:
            return jsonify({'success': True, 'message': 'No changes made'})

    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Token expired'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    

@auth_bp.route('/get_profile', methods=['POST'])
def get_profile():
    data = request.get_json()
    token = data.get('token')

    if not token:
        return jsonify({'success': False, 'message': 'Token missing'}), 401

    try:
        # Decode the JWT
        decoded = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        phone_or_email = decoded['user']

        # Fetch user info
        db = get_db()
        users_col = db['users']
        user = users_col.find_one({'phone_or_email': phone_or_email}, {'_id': 0})

        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        return jsonify({
            'success': True,
            'data': user
        })

    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Token expired'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400