import os, sqlite3, secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = os.getenv("UPI_ID", "denki@ybl") # Unga real UPI ID inga podunga

# Available Plans Configuration
PLANS = {
    "free": {"name": "Free", "price": 0, "limit": 150},
    "lite": {"name": "Lite", "price": 32, "limit": 1500},
    "basic": {"name": "Basic", "price": 59, "limit": 3000},
    "pro": {"name": "Pro", "price": 285, "limit": 25000}
}

def get_db():
    conn = sqlite3.connect('denki_api.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            api_key TEXT PRIMARY KEY,
            status TEXT,
            play_count INTEGER DEFAULT 0,
            max_limit INTEGER DEFAULT 150,
            utr_number TEXT,
            expiry_date TEXT,
            plan_name TEXT DEFAULT 'Free'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- USER ROUTES ---
@app.route('/')
def home():
    if 'my_key' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_key', methods=['POST'])
def get_key():
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key 
    conn = get_db()
    conn.execute('INSERT INTO api_keys (api_key, status, max_limit, utr_number, expiry_date, plan_name) VALUES (?, ?, ?, ?, ?, ?)',
                 (new_key, "active", PLANS["free"]["limit"], "NONE", "Lifetime", "Free"))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'my_key' not in session: return redirect(url_for('home'))
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    if not key_data:
        session.pop('my_key', None)
        return redirect(url_for('home'))
    return render_template('dashboard.html', key_data=key_data)

@app.route('/plans')
def plans():
    if 'my_key' not in session: return redirect(url_for('home'))
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    return render_template('plans.html', key_data=key_data)

@app.route('/billing')
def billing():
    if 'my_key' not in session: return redirect(url_for('home'))
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    return render_template('billing.html', key_data=key_data)

@app.route('/regenerate', methods=['POST'])
def regenerate():
    old_key = session.get('my_key')
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key
    conn = get_db()
    if old_key: conn.execute('DELETE FROM api_keys WHERE api_key=?', (old_key,))
    conn.execute('INSERT INTO api_keys (api_key, status, max_limit, utr_number, expiry_date, plan_name) VALUES (?, ?, ?, ?, ?, ?)',
                 (new_key, "active", PLANS["free"]["limit"], "NONE", "Lifetime", "Free"))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# --- PAYMENT ROUTES ---
@app.route('/checkout/<plan_id>')
def checkout(plan_id):
    if 'my_key' not in session: return redirect(url_for('home'))
    if plan_id not in PLANS or plan_id == "free": return redirect(url_for('plans'))
    
    plan = PLANS[plan_id]
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=upi://pay?pa={UPI_ID}%26pn=DenkiAPI%26am={plan['price']}%26cu=INR"
    
    return render_template('checkout.html', plan=plan, plan_id=plan_id, qr_url=qr_url)

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'my_key' not in session: return redirect(url_for('home'))
    
    utr = request.form.get('utr_number').strip()
    plan_id = request.form.get('plan_id')
    my_key = session['my_key']
    plan_name = PLANS[plan_id]["name"]
    
    conn = get_db()
    conn.execute('UPDATE api_keys SET status="pending", utr_number=?, plan_name=? WHERE api_key=?', 
                 (utr, f"Pending {plan_name}", my_key))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# --- ADMIN PANEL ---
@app.route('/admin')
def admin():
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Access Denied"
    conn = get_db()
    keys = conn.execute('SELECT * FROM api_keys ORDER BY rowid DESC').fetchall()
    conn.close()
    return render_template('admin.html', keys=keys, pwd=ADMIN_PASSWORD)

@app.route('/approve/<api_key>/<plan_name>')
def approve(api_key, plan_name):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    
    # Find the requested plan details
    clean_plan_name = plan_name.replace("Pending ", "")
    target_plan = next((p for p in PLANS.values() if p["name"] == clean_plan_name), PLANS["basic"])
    
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    new_premium_key = api_key.replace("TRIAL-", "DENKI-")
    
    conn = get_db()
    conn.execute('''
        UPDATE api_keys 
        SET status="active", api_key=?, expiry_date=?, play_count=0, max_limit=?, plan_name=? 
        WHERE api_key=?
    ''', (new_premium_key, expiry, target_plan["limit"], target_plan["name"], api_key))
    conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

# --- API VERIFICATION ---
@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    key = data.get('api_key')
    
    conn = get_db()
    user = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (key,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({"status": "invalid"}), 404

    if user['status'] == "active":
        if user['play_count'] < user['max_limit']:
            conn.execute('UPDATE api_keys SET play_count = play_count + 1 WHERE api_key=?', (key,))
            conn.commit()
            conn.close()
            return jsonify({"status": "active", "plan": user['plan_name'], "yt_key": OFFICIAL_GOOGLE_KEY}), 200
        else:
            conn.close()
            return jsonify({"status": "expired", "message": "Daily Limit Reached"}), 403

    conn.close()
    return jsonify({"status": "pending", "message": "Payment Verification Pending"}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
