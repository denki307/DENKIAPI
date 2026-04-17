import os, sqlite3, secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # Session tracking-kaga

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
OFFICIAL_GOOGLE_KEY = os.getenv("YT_API_KEY", "AIzaSy_UNGA_ORIGINAL_KEY_INGA")

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
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
            utr_number TEXT,
            expiry_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 1. HOME & GENERATE KEY (NO LOGIN)
# ==========================================
@app.route('/')
def home():
    # User kitta already key iruntha direct ah dashboard poidum
    if 'my_key' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_key', methods=['POST'])
def get_key():
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key # Browser-la key-ah save pandrom
    
    conn = get_db()
    conn.execute('INSERT INTO api_keys (api_key, status, play_count, utr_number, expiry_date) VALUES (?, ?, ?, ?, ?)',
                 (new_key, "trial", 0, "NONE", "NONE"))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# ==========================================
# 2. DASHBOARD (HIDE, COPY, REGENERATE)
# ==========================================
@app.route('/dashboard')
def dashboard():
    if 'my_key' not in session: return redirect(url_for('home'))
    
    my_key = session['my_key']
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (my_key,)).fetchone()
    conn.close()
    
    # DB-la key illana (admin delete panniruntha), home-ku thallidurom
    if not key_data:
        session.pop('my_key', None)
        return redirect(url_for('home'))
    
    upi_id = "denki@ybl" 
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=upi://pay?pa={upi_id}%26pn=DenkiAPI%26am=99%26cu=INR"
    
    return render_template('dashboard.html', key_data=key_data, qr_url=qr_url)

@app.route('/regenerate', methods=['POST'])
def regenerate():
    old_key = session.get('my_key')
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key
    
    conn = get_db()
    if old_key:
        conn.execute('DELETE FROM api_keys WHERE api_key=?', (old_key,)) # Pazhaiya key delete aagidum
        
    conn.execute('INSERT INTO api_keys (api_key, status, play_count, utr_number, expiry_date) VALUES (?, ?, ?, ?, ?)',
                 (new_key, "trial", 0, "NONE", "NONE"))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upgrade', methods=['POST'])
def upgrade():
    utr = request.form.get('utr_number').strip()
    my_key = session.get('my_key')
    
    if my_key:
        conn = get_db()
        conn.execute('UPDATE api_keys SET status="pending", utr_number=? WHERE api_key=?', (utr, my_key))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

# ==========================================
# 3. ADMIN PANEL
# ==========================================
@app.route('/admin')
def admin():
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Access Denied"
    conn = get_db()
    keys = conn.execute('SELECT * FROM api_keys ORDER BY rowid DESC').fetchall()
    conn.close()
    return render_template('admin.html', keys=keys, pwd=ADMIN_PASSWORD)

@app.route('/approve/<api_key>')
def approve(api_key):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    new_premium_key = api_key.replace("TRIAL-", "DENKI-")
    
    conn = get_db()
    conn.execute('UPDATE api_keys SET status="active", api_key=?, expiry_date=?, play_count=0 WHERE api_key=?', (new_premium_key, expiry, api_key))
    conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

# ==========================================
# 4. BOT API VERIFICATION
# ==========================================
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
        conn.close()
        return jsonify({"status": "active", "type": "premium", "yt_key": OFFICIAL_GOOGLE_KEY}), 200

    if user['status'] == "trial":
        if user['play_count'] < 100:
            conn.execute('UPDATE api_keys SET play_count = play_count + 1 WHERE api_key=?', (key,))
            conn.commit()
            conn.close()
            return jsonify({"status": "active", "type": "trial", "yt_key": None}), 200
        else:
            conn.close()
            return jsonify({"status": "expired", "message": "Trial Limit Reached"}), 403

    conn.close()
    return jsonify({"status": "pending"}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
