import os, sqlite3, secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # For session handling

# ==========================================
# CONFIGURATION (HEROKU CONFIG VARS-LA PODANUM)
# ==========================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
OFFICIAL_GOOGLE_KEY = os.getenv("YT_API_KEY", "AIzaSy_UNGA_ORIGINAL_KEY_INGA")

# Google OAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID", "UNGA_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "UNGA_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

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
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            api_key TEXT,
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
# 1. AUTHENTICATION & LOGIN (GOOGLE)
# ==========================================
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login')
def login():
    redirect_uri = url_for('auth', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth')
def auth():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    session['user'] = user_info
    
    email = user_info['email']
    name = user_info['name']
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    
    if not user:
        # First time login pandranga, auto-generate Trial Key
        trial_key = f"TRIAL-{secrets.token_hex(4).upper()}"
        conn.execute('INSERT INTO users (email, name, api_key, status, play_count, utr_number, expiry_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (email, name, trial_key, "trial", 0, "NONE", "NONE"))
        conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

# ==========================================
# 2. USER DASHBOARD (KEY, REGENERATE, UPGRADE)
# ==========================================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('home'))
    
    email = session['user']['email']
    conn = get_db()
    user_data = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    
    upi_id = "denki@ybl" # Mathikonga
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=upi://pay?pa={upi_id}%26pn=DenkiAPI%26am=99%26cu=INR"
    
    return render_template('dashboard.html', user=user_data, qr_url=qr_url)

@app.route('/regenerate', methods=['POST'])
def regenerate():
    if 'user' not in session: return redirect(url_for('home'))
    email = session['user']['email']
    
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    conn = get_db()
    conn.execute('UPDATE users SET api_key=?, status="trial", play_count=0 WHERE email=?', (new_key, email))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upgrade', methods=['POST'])
def upgrade():
    if 'user' not in session: return redirect(url_for('home'))
    
    utr = request.form.get('utr_number').strip()
    email = session['user']['email']
    
    conn = get_db()
    conn.execute('UPDATE users SET status="pending", utr_number=? WHERE email=?', (utr, email))
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
    users = conn.execute('SELECT * FROM users ORDER BY rowid DESC').fetchall()
    conn.close()
    return render_template('admin.html', users=users, pwd=ADMIN_PASSWORD)

@app.route('/approve/<email>')
def approve(email):
    if request.args.get('pwd') != ADMIN_PASSWORD: return "Denied"
    
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M')
    conn = get_db()
    # "TRIAL-" prefix-ah remove panni "DENKI-" nu premium look tharom
    user = conn.execute('SELECT api_key FROM users WHERE email=?', (email,)).fetchone()
    new_premium_key = user['api_key'].replace("TRIAL-", "DENKI-")
    
    conn.execute('UPDATE users SET status="active", api_key=?, expiry_date=?, play_count=0 WHERE email=?', (new_premium_key, expiry, email))
    conn.commit()
    conn.close()
    return redirect(url_for('admin', pwd=ADMIN_PASSWORD))

# ==========================================
# 4. BOT API VERIFICATION (The Gateway)
# ==========================================
@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    key = data.get('api_key')
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE api_key=?', (key,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({"status": "invalid"}), 404

    # PREMIUM USER
    if user['status'] == "active":
        conn.close()
        return jsonify({"status": "active", "type": "premium", "yt_key": OFFICIAL_GOOGLE_KEY}), 200

    # TRIAL USER
    if user['status'] == "trial":
        if user['play_count'] < 100:
            conn.execute('UPDATE users SET play_count = play_count + 1 WHERE api_key=?', (key,))
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

