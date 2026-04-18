import os, secrets, random, string
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

app = Flask(__name__)
# Permanent Secret Key
app.secret_key = "denki_ultra_secure_permanent_key_2026"

# Configuration
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = "denkielangokey@fam"
OFFICIAL_YT_KEY = os.getenv("YT_API_KEY", "AIzaSy_PUT_YOUR_KEY_HERE_IF_NOT_IN_HEROKU")

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/") 
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

# --- HELPER FUNCTION: Get Indian Standard Time (IST) ---
def ist_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

# --- SYNC LOGIC (Daily Reset & 30-Day Expiry) ---
def sync_user(user):
    today = ist_now().strftime('%Y-%m-%d')
    updates = {}
    
    if user.get('last_reset') != today:
        updates['play_count'] = 0
        updates['last_reset'] = today

    if user['plan_name'] != 'Free' and user['expiry_date'] != 'Lifetime':
        expiry_dt = datetime.strptime(user['expiry_date'], '%d %b %Y')
        if ist_now() > expiry_dt:
            updates['plan_name'] = 'Free'
            updates['max_limit'] = 150
            updates['expiry_date'] = 'Lifetime'
            updates['play_count'] = 0

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
        email = request.form.get('email').lower().strip()
        pw = request.form.get('password')
        cpw = request.form.get('confirm_password')

        if pw != cpw: return render_template('register.html', error="Passwords do not match!")
        if users_col.find_one({'email': email}): return render_template('register.html', error="Email exists!")

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
        email = request.form.get('email').lower().strip()
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

# --- CORE ROUTES ---
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
        delta = datetime.strptime(user['expiry_date'], '%d %b %Y') - ist_now()
        days_left = f"{max(0, delta.days)} days left"
        
    return render_template('dashboard.html', user=user, days_left=days_left)

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'email' not in session: return redirect(url_for('login'))
    user = users_col.find_one({'email': session['email']})
    if request.method == 'POST':
        utr, amt = request.form.get('utr').strip(), int(request.form.get('amount'))
        tx_col.insert_one({
            "email": user['email'], "username": user['username'], "utr": utr, 
            "amount": amt, "status": "pending", "date": ist_now().strftime('%d %b, %I:%M %p')
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

# --- BOT API ENDPOINT ---
@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.get_json(silent=True) or {}
    key = data.get('api_key')
    if not key: return jsonify({"status": "invalid", "reason": "No API key provided"}), 400
    
    user = users_col.find_one({'api_key': key})
    if not user: return jsonify({"status": "invalid"}), 404
    
    user = sync_user(user)
    if user['play_count'] < user['max_limit']:
        users_col.update_one({'api_key': user['api_key']}, {'$inc': {'play_count': 1}})
        return jsonify({"status": "success", "plan": user['plan_name'], "yt_key": OFFICIAL_YT_KEY}), 200
        
    return jsonify({"status": "limit_reached", "reason": "Daily limit exceeded"}), 403

# --- ADMIN PANEL ---
@app.route('/admin')
def admin():
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    pending = list(tx_col.find({'status': 'pending'}).sort('_id', -1))
    return render_template('admin.html', pending=pending, pwd=ADMIN_PASSWORD)

@app.route('/admin_action/<tid>/<action>')
def admin_action(tid, action):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    tx = tx_col.find_one({'_id': ObjectId(tid)})
    if tx and tx['status'] == 'pending':
        if action == 'approve':
            users_col.update_one({'email': tx['email']}, {'$inc': {'balance': tx['amount']}})
            tx_col.update_one({'_id': ObjectId(tid)}, {'$set': {'status': 'approved'}})
        else:
            tx_col.update_one({'_id': ObjectId(tid)}, {'$set': {'status': 'rejected'}})
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

