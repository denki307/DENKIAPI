import os, sqlite3, secrets, random, string
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
# Permanent key so sessions don't drop
app.secret_key = "denki_mega_secure_secret_fixed_2026"

ADMIN_PASSWORD = "boss"
UPI_ID = "denkielangokey@fam"
OFFICIAL_YT_KEY = os.getenv("YT_API_KEY", "AIzaSyDV4lSw3PHOCdl20dDY_e7bkp3xXXc_FD4")

PLANS = {
    "lite": {"name": "Lite", "price": 32, "limit": 1500},
    "basic": {"name": "Basic", "price": 59, "limit": 3000},
    "pro": {"name": "Pro", "price": 285, "limit": 25000},
    "ultra": {"name": "Ultra", "price": 2389, "limit": 150000}
}

def get_db():
    conn = sqlite3.connect('denki_api.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, api_key TEXT, balance INTEGER DEFAULT 0,
        play_count INTEGER DEFAULT 0, max_limit INTEGER DEFAULT 150,
        plan_name TEXT DEFAULT 'Free', expiry_date TEXT DEFAULT 'Lifetime',
        last_reset TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, 
        utr TEXT, amount INTEGER, status TEXT DEFAULT 'pending', date TEXT
    )''')
    conn.commit()
    conn.close()

# Logic to check expiry and reset daily counts
def sync_user_status(user_row):
    conn = get_db()
    username = user_row['username']
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Midnight Reset (Daily limit reset)
    if user_row['last_reset'] != today:
        conn.execute('UPDATE users SET play_count = 0, last_reset = ? WHERE username = ?', (today, username))
        conn.commit()

    # 2. Expiry Check (Auto Downgrade)
    if user_row['plan_name'] != 'Free' and user_row['expiry_date'] != 'Lifetime':
        expiry_dt = datetime.strptime(user_row['expiry_date'], '%d %b %Y')
        if datetime.now() > expiry_dt:
            # Plan expired! Downgrade to Free
            conn.execute('''UPDATE users SET plan_name = 'Free', max_limit = 150, 
                            expiry_date = 'Lifetime' WHERE username = ?''', (username,))
            conn.commit()
    
    updated_user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    return updated_user

init_db()

# --- ROUTES ---

@app.route('/')
def index():
    if 'username' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_started')
def get_started():
    if 'username' not in session:
        new_user = "Denki_" + ''.join(random.choices(string.digits, k=5))
        new_key = f"DENKI-{secrets.token_hex(6).upper()}"
        today = datetime.now().strftime('%Y-%m-%d')
        conn = get_db()
        conn.execute('INSERT INTO users (username, api_key, last_reset) VALUES (?, ?, ?)', 
                     (new_user, new_key, today))
        conn.commit()
        conn.close()
        session['username'] = new_user
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('index'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username=?', (session['username'],)).fetchone()
    conn.close()
    if not user: return redirect(url_for('logout'))
    
    # Check for live updates (Expiry/Reset)
    user = sync_user_status(user)
    
    # Calculate days remaining for UI
    days_left = "∞"
    if user['expiry_date'] != 'Lifetime':
        delta = datetime.strptime(user['expiry_date'], '%d %b %Y') - datetime.now()
        days_left = f"{max(0, delta.days)} days remaining"

    return render_template('dashboard.html', user=user, days_left=days_left)

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'username' not in session: return redirect(url_for('index'))
    conn = get_db()
    if request.method == 'POST':
        utr, amt = request.form.get('utr'), request.form.get('amount')
        date = datetime.now().strftime('%d %b %Y, %I:%M %p')
        conn.execute('INSERT INTO transactions (username, utr, amount, date) VALUES (?, ?, ?, ?)', 
                     (session['username'], utr, amt, date))
        conn.commit()
    
    user = conn.execute('SELECT * FROM users WHERE username=?', (session['username'],)).fetchone()
    txs = conn.execute('SELECT * FROM transactions WHERE username=? ORDER BY id DESC', (session['username'],)).fetchall()
    conn.close()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={UPI_ID}%26pn=DenkiAPI"
    return render_template('billing.html', user=user, txs=txs, qr_url=qr_url)

@app.route('/plans')
def plans():
    if 'username' not in session: return redirect(url_for('index'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username=?', (session['username'],)).fetchone()
    conn.close()
    return render_template('plans.html', user=user, plans=PLANS)

@app.route('/buy_plan/<plan_id>')
def buy_plan(plan_id):
    if 'username' not in session or plan_id not in PLANS: return redirect(url_for('plans'))
    plan = PLANS[plan_id]
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username=?', (session['username'],)).fetchone()
    if user['balance'] >= plan['price']:
        new_bal = user['balance'] - plan['price']
        expiry = (datetime.now() + timedelta(days=30)).strftime('%d %b %Y')
        conn.execute('''UPDATE users SET balance=?, plan_name=?, max_limit=?, expiry_date=?, play_count=0 
                        WHERE username=?''', (new_bal, plan['name'], plan['limit'], expiry, session['username']))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- BOT API VERIFICATION ENDPOINT ---
@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    key = data.get('api_key')
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE api_key=?', (key,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({"status": "invalid"}), 404

    # Run sync check on every API call
    user = sync_user_status(user)

    if user['play_count'] < user['max_limit']:
        conn = get_db()
        conn.execute('UPDATE users SET play_count = play_count + 1 WHERE api_key=?', (key,))
        conn.commit()
        conn.close()
        return jsonify({
            "status": "success", 
            "plan": user['plan_name'], 
            "remaining": user['max_limit'] - (user['play_count'] + 1),
            "yt_key": OFFICIAL_YT_KEY
        }), 200
    else:
        conn.close()
        return jsonify({"status": "failed", "reason": "Daily Limit Reached. Upgrade Plan."}), 403

# --- ADMIN PANEL ---
@app.route('/admin')
def admin():
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Access Denied"
    conn = get_db()
    pending = conn.execute('SELECT * FROM transactions WHERE status="pending" ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('admin.html', pending=pending, pwd=ADMIN_PASSWORD)

@app.route('/admin_action/<int:tx_id>/<action>')
def admin_action(tx_id, action):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    conn = get_db()
    tx = conn.execute('SELECT * FROM transactions WHERE id=?', (tx_id,)).fetchone()
    if tx and tx['status'] == 'pending':
        if action == 'approve':
            conn.execute('UPDATE users SET balance = balance + ? WHERE username=?', (tx['amount'], tx['username']))
            conn.execute('UPDATE transactions SET status="approved" WHERE id=?', (tx_id,))
        else:
            conn.execute('UPDATE transactions SET status="rejected" WHERE id=?', (tx_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

