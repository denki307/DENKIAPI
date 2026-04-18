import os, sqlite3, secrets, random, string
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
# FIXED: Static Secret Key (Ippo session eppavum drop aagathu)
app.secret_key = "denki_super_secret_key_2026_fixed"

ADMIN_PASSWORD = "boss"
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
    # Puthusa Username system
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        api_key TEXT, 
        balance INTEGER DEFAULT 0,
        play_count INTEGER DEFAULT 0, 
        max_limit INTEGER DEFAULT 150,
        plan_name TEXT DEFAULT 'Free', 
        expiry_date TEXT DEFAULT 'Lifetime'
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT, 
        utr TEXT, 
        amount INTEGER, 
        status TEXT DEFAULT 'pending', 
        date TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- USER ROUTES ---
@app.route('/')
def index():
    if 'username' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_started')
def get_started():
    if 'username' not in session:
        # Thani thani Username generate pandrom (e.g. Denki_48291)
        new_username = "Denki_" + ''.join(random.choices(string.digits, k=5))
        new_key = f"DENKI-{secrets.token_hex(6).upper()}"
        
        session['username'] = new_username
        conn = get_db()
        conn.execute('INSERT INTO users (username, api_key) VALUES (?, ?)', (new_username, new_key))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('index'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username=?', (session['username'],)).fetchone()
    conn.close()
    if not user:
        session.pop('username', None)
        return redirect(url_for('index'))
    return render_template('dashboard.html', user=user)

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'username' not in session: return redirect(url_for('index'))
    conn = get_db()
    
    if request.method == 'POST':
        utr = request.form.get('utr').strip()
        amt = request.form.get('amount')
        date = datetime.now().strftime('%d %b %Y, %I:%M %p')
        conn.execute('INSERT INTO transactions (username, utr, amount, status, date) VALUES (?, ?, ?, ?, ?)', 
                     (session['username'], utr, amt, 'pending', date))
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
    
    # Check balance and deduct EXACT amount
    if user['balance'] >= plan['price']:
        new_balance = user['balance'] - plan['price']
        expiry = (datetime.now() + timedelta(days=30)).strftime('%d %b %Y')
        conn.execute('''UPDATE users SET balance=?, plan_name=?, max_limit=?, expiry_date=?, play_count=0 
                        WHERE username=?''', (new_balance, plan['name'], plan['limit'], expiry, session['username']))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

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
            # Add exact amount to the SPECIFIC USER'S wallet
            conn.execute('UPDATE users SET balance = balance + ? WHERE username=?', (tx['amount'], tx['username']))
            conn.execute('UPDATE transactions SET status="approved" WHERE id=?', (tx_id,))
        else:
            conn.execute('UPDATE transactions SET status="rejected" WHERE id=?', (tx_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

