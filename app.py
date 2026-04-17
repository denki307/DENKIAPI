from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import secrets
from datetime import datetime, timedelta

app = Flask(__name__)
ADMIN_PASSWORD = "boss" # Admin page-ku password

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
def init_db():
    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            api_key TEXT UNIQUE,
            status TEXT,
            play_count INTEGER DEFAULT 0,
            expiry_date TEXT,
            utr_number TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 1. FRONTEND DASHBOARD
# ==========================================
@app.route('/')
def home():
    upi_id = "UNGA_UPI_ID@ybl" # INGA UNGA UPI ID PODUNGA
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=upi://pay?pa={upi_id}%26pn=PremiumAPI%26am=99%26cu=INR"
    return render_template('index.html', qr_url=qr_url)

# ==========================================
# 2. GENERATE FREE TRIAL KEY (100 SONGS)
# ==========================================
@app.route('/get_trial', methods=['POST'])
def get_trial():
    user_name = request.form.get('user_name')
    if not user_name:
        return "Error: Name required!", 400

    trial_key = f"TRIAL-{secrets.token_hex(6).upper()}"
    
    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('INSERT INTO api_keys (user_name, api_key, status, play_count, expiry_date, utr_number) VALUES (?, ?, ?, 0, ?, ?)',
              (user_name, trial_key, "trial", "Free Limit: 100 Songs", "NONE"))
    conn.commit()
    conn.close()

    return f"""
    <div style="background:#1a1a2e; color:#fff; padding:50px; text-align:center; font-family:sans-serif;">
        <h2 style="color:#00ffcc;">🎉 Trial Key Generated!</h2>
        <p>Hi {user_name}, your free key for 100 songs is:</p>
        <h1 style="background:#000; padding:20px; border:2px dashed #00ffcc; display:inline-block;">{trial_key}</h1>
        <br><br><a href="/" style="color:#ff9a9e; text-decoration:none; font-size:1.2rem;">⬅ Go Back</a>
    </div>
    """

# ==========================================
# 3. UPGRADE TO PREMIUM (SUBMIT UTR)
# ==========================================
@app.route('/upgrade', methods=['POST'])
def upgrade_key():
    existing_api_key = request.form.get('api_key')
    utr_number = request.form.get('utr_number')

    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('SELECT id FROM api_keys WHERE api_key = ?', (existing_api_key,))
    key_exists = c.fetchone()

    if not key_exists:
        return "Error: Invalid API Key!", 404

    c.execute('UPDATE api_keys SET status = ?, utr_number = ? WHERE api_key = ?', 
              ("pending", utr_number, existing_api_key))
    conn.commit()
    conn.close()

    return f"""
    <div style="background:#1a1a2e; color:#fff; padding:50px; text-align:center; font-family:sans-serif;">
        <h2 style="color:#ff9a9e;">⏳ Payment Under Review</h2>
        <p>Your UTR (<b>{utr_number}</b>) for Key <b>{existing_api_key}</b> has been submitted.</p>
        <p>It will become UNLIMITED once the admin approves it.</p>
        <br><a href="/" style="color:#00ffcc; text-decoration:none; font-size:1.2rem;">⬅ Go Back</a>
    </div>
    """

# ==========================================
# 4. ADMIN PANEL (APPROVE KEYS)
# ==========================================
@app.route('/admin')
def admin_panel():
    pwd = request.args.get('pwd')
    if pwd != ADMIN_PASSWORD:
        return "❌ Access Denied!"

    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('SELECT id, user_name, api_key, status, play_count, utr_number, expiry_date FROM api_keys ORDER BY id DESC')
    keys = c.fetchall()
    conn.close()
    
    return render_template('admin.html', keys=keys, pwd=pwd)

@app.route('/approve/<int:key_id>')
def approve_key(key_id):
    pwd = request.args.get('pwd')
    if pwd != ADMIN_PASSWORD:
        return "Access Denied!"

    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('UPDATE api_keys SET status = ?, expiry_date = ?, play_count = 0 WHERE id = ?', ("active", expiry_date, key_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_panel', pwd=pwd))

# ==========================================
# 5. API VERIFICATION ENDPOINT
# ==========================================
@app.route('/api/verify', methods=['POST'])
def verify_key():
    data = request.json
    api_key = data.get('api_key')
    
    conn = sqlite3.connect('anime_music_api.db')
    c = conn.cursor()
    c.execute('SELECT status, play_count, expiry_date FROM api_keys WHERE api_key = ?', (api_key,))
    result = c.fetchone()

    if not result:
        conn.close()
        return jsonify({"status": "invalid", "message": "Key not found!"}), 404

    status, play_count, expiry_date = result

    if status == "trial":
        if play_count < 100:
            new_count = play_count + 1
            c.execute('UPDATE api_keys SET play_count = ? WHERE api_key = ?', (new_count, api_key))
            conn.commit()
            conn.close()
            return jsonify({"status": "active", "message": f"Trial Active. {100 - new_count} songs left."}), 200
        else:
            c.execute('UPDATE api_keys SET status = ? WHERE api_key = ?', ("limit_reached", api_key))
            conn.commit()
            conn.close()
            return jsonify({"status": "expired", "message": "100 Songs Free Limit Reached! Pay to upgrade."}), 403

    if status == "pending":
        conn.close()
        return jsonify({"status": "error", "message": "Payment verification pending by Admin."}), 403

    if status == "active":
        if datetime.now() > datetime.strptime(expiry_date, '%Y-%m-%d %H:%M:%S'):
            c.execute('UPDATE api_keys SET status = ? WHERE api_key = ?', ("expired", api_key))
            conn.commit()
            conn.close()
            return jsonify({"status": "expired", "message": "Premium Subscription Expired!"}), 403
            
        conn.close()
        return jsonify({"status": "active", "message": "Premium Unlimited Access."}), 200

    conn.close()
    return jsonify({"status": "invalid"}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

