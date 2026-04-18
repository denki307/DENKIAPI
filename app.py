import os, secrets, random, string, requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

app = Flask(__name__)
# Permanent Secret Key so sessions don't expire
app.secret_key = "denki_ultra_secure_permanent_key_2026"

# --- CONFIGURATION ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = "denkielangokey@fam"
# Your Official YouTube API Key from Google Cloud
OFFICIAL_YT_KEY = os.getenv("YT_API_KEY", "AIzaSyDV4lSw3PHOCdl20dDY_e7bkp3xXXc_FD4")

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Devilsirophai:devilbhaiontop@devil0.d9epxqw.mongodb.net/?appName=Devil0") 
client = MongoClient(MONGO_URI)
db = client['denki_platform']
users_col = db['users']
tx_col = db['transactions']

PLANS = {
    "lite": {"name": "Lite", "price": 32, "limit": 1500},
    "basic": {"name": "Basic", "price": 59, "limit": 3000},
    "pro": {"name": "Pro", "price": 285, "limit": 25000},
    "ultra": {"name": "Ultra", "price": 2389, "limit": 150000}
}

# --- HELPER FUNCTIONS ---
def ist_now():
    # Convert UTC to Indian Standard Time
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def sync_user(user):
    today = ist_now().strftime('%Y-%m-%d')
    updates = {}
    
    # Midnight Reset: Play count will go back to 0 daily
    if user.get('last_reset') != today:
        updates['play_count'] = 0
        updates['last_reset'] = today

    # 30-Day Expiry: Move to Free plan if expired
    if user['plan_name'] != 'Free' and user['expiry_date'] != 'Lifetime':
        expiry_dt = datetime.strptime(user['expiry_date'], '%d %b %Y')
        if ist_now() > expiry_dt:
            updates.update({
                'plan_name': 'Free',
                'max_limit': 150,
                'expiry_date': 'Lifetime',
                'play_count': 0
            })

    if updates:
        users_col.update_one({'email': user['email']}, {'$set': updates})
        return users_col.find_one({'email': user['email']})
    return user

# --- AUTH ROUTES ---
@app.route('/')
def index():
    if 'email' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'email' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        pw = request.form.get('password')
        cpw = request.form.get('confirm_password')

        if not email or not pw: return render_template('register.html', error="All fields required!")
        if pw != cpw: return render_template('register.html', error="Passwords do not match!")
        if users_col.find_one({'email': email}): return render_template('register.html', error="Email already exists!")

        uname = "Denki_" + ''.join(random.choices(string.digits, k=5))
        key = f"DENKI-{secrets.token_hex(6).upper()}"
        
        users_col.insert_one({
            "email": email, "password": generate_password_hash(pw), "username": uname,
            "api_key": key, "balance": 0, "play_count": 0, "max_limit": 150,
            "plan_name": "Free", "expiry_date": "Lifetime", "last_reset": ist_now().strftime('%Y-%m-%d')
        })
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'email' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        pw = request.form.get('password')
        user = users_col.find_one({'email': email})
        if user and check_password_hash(user['password'], pw):
            session['email'] = email
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid credentials!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- DASHBOARD & LIVE STATS ---
@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect(url_for('login'))
    user = users_col.find_one({'email': session['email']})
    if not user:
        session.clear()
        return redirect(url_for('login'))
    user = sync_user(user)
    
    days_left = "∞"
    if user['expiry_date'] != 'Lifetime':
        try:
            delta = datetime.strptime(user['expiry_date'], '%d %b %Y') - ist_now()
            days_left = f"{max(0, delta.days)} days left"
        except: days_left = "Expired"
        
    return render_template('dashboard.html', user=user, days_left=days_left)

@app.route('/api/stats')
def get_stats():
    if 'email' not in session: return jsonify({}), 401
    user = sync_user(users_col.find_one({'email': session['email']}))
    return jsonify({
        "play_count": user['play_count'],
        "max_limit": user['max_limit'],
        "balance": user['balance']
    })

# --- PROXY YOUTUBE API (THE CONNECTOR) ---
@app.route('/youtube/v3/search', methods=['GET'])
def proxy_youtube():
    # Bot calls: unga-app.com/youtube/v3/search?q=SONG&key=DENKI-KEY
    bot_sent_key = request.args.get('key')
    
    if not bot_sent_key:
        return jsonify({"error": {"message": "API Key Missing"}}), 400

    user = users_col.find_one({'api_key': bot_sent_key})
    if not user:
        return jsonify({"error": {"message": "Invalid Denki API Key"}}), 403

    user = sync_user(user)
    if user['play_count'] >= user['max_limit']:
        return jsonify({"error": {"message": "Daily Limit Reached. Upgrade Plan."}}), 403

    # Success: Increment usage in DB
    users_col.update_one({'api_key': bot_sent_key}, {'$inc': {'play_count': 1}})

    # Forward the request to Google with your Official Key
    yt_url = "https://www.googleapis.com/youtube/v3/search"
    params = dict(request.args)
    params['key'] = OFFICIAL_YT_KEY
    
    # Ensure mandatory fields for bots are present
    if 'part' not in params: params['part'] = 'snippet'
    if 'type' not in params: params['type'] = 'video'
    
    try:
        # Mocking a real browser headers to avoid blocks
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(yt_url, params=params, headers=headers, timeout=15)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": "Internal Proxy Error", "details": str(e)}), 500

# --- BILLING & PAYMENTS ---
@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'email' not in session: return redirect(url_for('login'))
    user = users_col.find_one({'email': session['email']})
    if request.method == 'POST':
        utr = request.form.get('utr', '').strip()
        amt = request.form.get('amount', '0')
        if utr and amt.isdigit() and int(amt) > 0:
            tx_col.insert_one({
                "email": user['email'], "username": user['username'], "utr": utr, 
                "amount": int(amt), "status": "pending", "date": ist_now().strftime('%d %b, %H:%M')
            })
    txs = list(tx_col.find({'email': user['email']}).sort('_id', -1))
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={UPI_ID}%26pn=DenkiAPI"
    return render_template('billing.html', user=user, txs=txs, qr_url=qr_url)

@app.route('/plans')
def plans():
    if 'email' not in session: return redirect(url_for('login'))
    user = users_col.find_one({'email': session['email']})
    return render_template('plans.html', user=user, plans=PLANS)

@app.route('/buy_plan/<plan_id>')
def buy_plan(plan_id):
    if 'email' not in session or plan_id not in PLANS: return redirect(url_for('plans'))
    plan = PLANS[plan_id]
    user = users_col.find_one({'email': session['email']})
    
    if user['balance'] >= plan['price']:
        expiry = (ist_now() + timedelta(days=30)).strftime('%d %b %Y')
        users_col.update_one({'email': user['email']}, {
            '$inc': {'balance': -plan['price']},
            '$set': {'plan_name': plan['name'], 'max_limit': plan['limit'], 'expiry_date': expiry, 'play_count': 0}
        })
    return redirect(url_for('dashboard'))

# --- ADMIN PANEL ---
@app.route('/admin')
def admin():
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Access Denied", 403
    pending = list(tx_col.find({'status': 'pending'}).sort('_id', -1))
    return render_template('admin.html', pending=pending, pwd=ADMIN_PASSWORD)

@app.route('/admin_action/<tid>/<action>')
def admin_action(tid, action):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied", 403
    try:
        tx = tx_col.find_one({'_id': ObjectId(tid)})
        if tx and tx['status'] == 'pending':
            if action == 'approve':
                users_col.update_one({'email': tx['email']}, {'$inc': {'balance': tx['amount']}})
                tx_col.update_one({'_id': ObjectId(tid)}, {'$set': {'status': 'approved'}})
            else:
                tx_col.update_one({'_id': ObjectId(tid)}, {'$set': {'status': 'rejected'}})
    except: pass
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

