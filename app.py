import os, sqlite3, secrets
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
OFFICIAL_GOOGLE_KEY = os.getenv("YT_API_KEY", "AIzaSy_UNGA_ORIGINAL_KEY_INGA")

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

# --- ROUTES ---

@app.route('/')
def home():
    if 'my_key' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/get_key', methods=['POST'])
def get_key():
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key 
    conn = get_db()
    conn.execute('INSERT INTO api_keys (api_key, status, play_count, utr_number, expiry_date) VALUES (?, ?, ?, ?, ?)',
                 (new_key, "trial", 0, "NONE", "NONE"))
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

@app.route('/billing')
def billing():
    if 'my_key' not in session: return redirect(url_for('home'))
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    return render_template('billing.html', key_data=key_data)

@app.route('/plans')
def plans():
    if 'my_key' not in session: return redirect(url_for('home'))
    conn = get_db()
    key_data = conn.execute('SELECT * FROM api_keys WHERE api_key=?', (session['my_key'],)).fetchone()
    conn.close()
    return render_template('plans.html', key_data=key_data)

@app.route('/regenerate', methods=['POST'])
def regenerate():
    old_key = session.get('my_key')
    new_key = f"TRIAL-{secrets.token_hex(4).upper()}"
    session['my_key'] = new_key
    conn = get_db()
    if old_key: conn.execute('DELETE FROM api_keys WHERE api_key=?', (old_key,))
    conn.execute('INSERT INTO api_keys (api_key, status, play_count, utr_number, expiry_date) VALUES (?, ?, ?, ?, ?)',
                 (new_key, "trial", 0, "NONE", "NONE"))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

