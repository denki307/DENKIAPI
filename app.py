import os, secrets, random, string, requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, make_response
from datetime import datetime, timedelta
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = "denki_ultra_secure_permanent_key_2026"

# --- CONFIGURATION ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = "denkielangokey@fam"
OFFICIAL_YT_KEY = os.getenv("YT_API_KEY", "AIzaSyDV4lSw3PHOCdl20dDY_e7bkp3xXXc_FD4")

# MongoDB Connection
MONGO_URI = "mongodb+srv://Devilsirophai:devilbhaiontop@devil0.d9epxqw.mongodb.net/?appName=Devil0"
client = MongoClient(MONGO_URI)
db = client['denki_platform']
users_col = db['users']
tx_col = db['transactions']

PLANS = {"lite": 1500, "basic": 3000, "pro": 25000, "ultra": 150000}

def ist_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def sync_user(user):
    today = ist_now().strftime('%Y-%m-%d')
    updates = {}
    if user.get('last_reset') != today:
        updates['play_count'] = 0
        updates['last_reset'] = today
    if user['plan_name'] != 'Free' and user['expiry_date'] != 'Lifetime':
        expiry_dt = datetime.strptime(user['expiry_date'], '%d %b %Y')
        if ist_now() > expiry_dt:
            updates.update({'plan_name': 'Free', 'max_limit': 150, 'expiry_date': 'Lifetime', 'play_count': 0})
    if updates:
        users_col.update_one({'email': user['email']}, {'$set': updates})
        return users_col.find_one({'email': user['email']})
    return user

# --- PROXY YOUTUBE API (ULTRA COMPATIBLE VERSION) ---
@app.route('/youtube/v3/search', methods=['GET'])
def proxy_youtube():
    # 1. API Key check
    bot_sent_key = request.args.get('key')
    if not bot_sent_key:
        return jsonify({"error": {"message": "API Key Missing"}}), 400

    user = users_col.find_one({'api_key': bot_sent_key})
    if not user:
        return jsonify({"error": {"message": "Invalid API Key"}}), 403

    user = sync_user(user)
    if user['play_count'] >= user['max_limit']:
        return jsonify({"error": {"message": "Daily Limit Reached"}}), 403

    # 2. Database count update
    users_col.update_one({'api_key': bot_sent_key}, {'$inc': {'play_count': 1}})

    # 3. Requesting Official Google API
    yt_params = dict(request.args)
    yt_params['key'] = OFFICIAL_YT_KEY # Denki key-ah Official key-ah maathiduvom
    
    # AviaxMusic bot-ku snippet detail romba mukkiyam
    if 'part' not in yt_params: yt_params['part'] = 'snippet'
    if 'type' not in yt_params: yt_params['type'] = 'video'

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=yt_params, headers=headers, timeout=15)
        
        # Inga thaan namma JSON-ah pathila tharoom
        yt_json = r.json()
        
        # Bot "line 1 column 1" error adikkama irukka perfect JSON force pandroom
        response = make_response(jsonify(yt_json))
        response.headers['Content-Type'] = 'application/json'
        return response
    except Exception as e:
        # Request fail aana kooda namma JSON thaan anuppanum
        return jsonify({"error": "Proxy Error", "details": str(e)}), 500

# --- OTHER ROUTES ---
@app.route('/')
def index():
    if 'email' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email, pw, cpw = request.form.get('email', '').lower().strip(), request.form.get('password'), request.form.get('confirm_password')
        if pw != cpw: return render_template('register.html', error="Passwords do not match!")
        if users_col.find_one({'email': email}): return render_template('register.html', error="Email exists!")
        key = f"DENKI-{secrets.token_hex(6).upper()}"
        users_col.insert_one({"email": email, "password": generate_password_hash(pw), "username": "Denki_"+''.join(random.choices(string.digits, k=5)), "api_key": key, "balance": 0, "play_count": 0, "max_limit": 150, "plan_name": "Free", "expiry_date": "Lifetime", "last_reset": ist_now().strftime('%Y-%m-%d')})
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, pw = request.form.get('email', '').lower().strip(), request.form.get('password')
        user = users_col.find_one({'email': email})
        if user and check_password_hash(user['password'], pw):
            session['email'] = email
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Login!")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect(url_for('login'))
    user = sync_user(users_col.find_one({'email': session['email']}))
    return render_template('dashboard.html', user=user, days_left="∞")

@app.route('/api/stats')
def get_stats():
    if 'email' not in session: return jsonify({}), 401
    user = sync_user(users_col.find_one({'email': session['email']}))
    return jsonify({"play_count": user['play_count'], "max_limit": user['max_limit'], "balance": user['balance']})

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'email' not in session: return redirect(url_for('login'))
    user = users_col.find_one({'email': session['email']})
    if request.method == 'POST':
        tx_col.insert_one({"email": user['email'], "username": user['username'], "utr": request.form.get('utr'), "amount": int(request.form.get('amount', 0)), "status": "pending", "date": ist_now().strftime('%d %b, %H:%M')})
    return render_template('billing.html', user=user, txs=list(tx_col.find({'email': user['email']}).sort('_id', -1)), qr_url=f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={UPI_ID}")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
