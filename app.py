import os, sqlite3, secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = "denkielangokey@fam"

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
    conn.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        api_key TEXT PRIMARY KEY, status TEXT, balance INTEGER DEFAULT 0,
        play_count INTEGER DEFAULT 0, max_limit INTEGER DEFAULT 150,
        plan_name TEXT DEFAULT 'Free', expiry_date TEXT DEFAULT 'Lifetime'
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, api_key TEXT, 
        utr TEXT, amount INTEGER, status TEXT DEFAULT 'pending', date TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- USER ROUTES ---
@app.route('/')
def index():
    if 'my_key' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_started')
def get_started():
    if 'my_key' not in session:
        new_key = f"DENKI-{secrets.token_hex(4).upper()}"
        session['my_key'] = new_key
        conn = get_db()
        conn.execute('INSERT OR IGNORE INTO api_keys (api_key, status) VALUES (?, ?)', (new_key, "active"))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'my_key' not in session: return redirect(url_for('index'))
    conn = get_db()
    user = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    if not user:
        session.pop('my_key', None)
        return redirect(url_for('index'))
    return render_template('dashboard.html', user=user)

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'my_key' not in session: return redirect(url_for('index'))
    conn = get_db()
    if request.method == 'POST':
        utr = request.form.get('utr').strip()
        amt = request.form.get('amount')
        date = datetime.now().strftime('%d %b %Y')
        conn.execute('INSERT INTO transactions (api_key, utr, amount, status, date) VALUES (?, ?, ?, ?, ?)', 
                     (session['my_key'], utr, amt, 'pending', date))
        conn.commit()
    
    user = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    txs = conn.execute('SELECT * FROM transactions WHERE api_key=? ORDER BY id DESC', (session['my_key'],)).fetchall()
    conn.close()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={UPI_ID}%26pn=DenkiAPI"
    return render_template('billing.html', user=user, txs=txs, qr_url=qr_url)

@app.route('/plans')
def plans():
    if 'my_key' not in session: return redirect(url_for('index'))
    conn = get_db()
    user = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    return render_template('plans.html', user=user, plans=PLANS)

@app.route('/buy_plan/<plan_id>')
def buy_plan(plan_id):
    if 'my_key' not in session or plan_id not in PLANS: return redirect(url_for('plans'))
    plan = PLANS[plan_id]
    conn = get_db()
    user = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    
    # Check if user has enough balance
    if user['balance'] >= plan['price']:
        new_balance = user['balance'] - plan['price']
        expiry = (datetime.now() + timedelta(days=30)).strftime('%d %b %Y')
        conn.execute('''UPDATE api_keys SET balance=?, plan_name=?, max_limit=?, expiry_date=?, play_count=0 
                        WHERE api_key=?''', (new_balance, plan['name'], plan['limit'], expiry, session['my_key']))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# --- ADMIN ROUTES ---
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
            conn.execute('UPDATE api_keys SET balance = balance + ? WHERE api_key=?', (tx['amount'], tx['api_key']))
            conn.execute('UPDATE transactions SET status="approved" WHERE id=?', (tx_id,))
        else:
            conn.execute('UPDATE transactions SET status="rejected" WHERE id=?', (tx_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

