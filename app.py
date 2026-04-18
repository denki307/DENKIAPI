import os, secrets, random, string, requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, make_response
from datetime import datetime, timedelta
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = "denki_ultra_secure_permanent_key_2026"

# --- CONFIGURATION ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "boss")
UPI_ID = "denkielangokey@fam"
OFFICIAL_YT_KEY = os.getenv("YT_API_KEY", "AIzaSyDV4lSw3PHOCdl20dDY_e7bkp3xXXc_FD4")

# MongoDB
MONGO_URI = "mongodb+srv://Devilsirophai:devilbhaiontop@devil0.d9epxqw.mongodb.net/?appName=Devil0"
client = MongoClient(MONGO_URI)
db = client['denki_platform']
users_col = db['users']
tx_col = db['transactions']

PLANS = {"lite": 1500, "basic": 3000, "pro": 25000, "ultra": 150000}

def ist_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def sync_user(user):
    today = ist_now().strftime('%Y-%m-%d')
    updates = {}
    if user.get('last_reset') != today:
        updates['play_count'] = 0
        updates['last_reset'] = today
    if user['plan_name'] != 'Free' and user['expiry_date'] != 'Lifetime':
        expiry_dt = datetime.strptime(user['expiry_date'], '%d %b %Y')
        if ist_now() > expiry_dt:
            updates.update({'plan_name': 'Free', 'max_limit': 150, 'expiry_date': 'Lifetime', 'play_count': 0})
    if updates:
        users_col.update_one({'email': user['email']}, {'$set': updates})
        return users_col.find_one({'email': user['email']})
    return user

@app.errorhandler(404)
def not_found(e):
    resp = make_response(jsonify({"error": "Endpoint not found"}))
    resp.headers['Content-Type'] = 'application/json'
    return resp, 404

# =======================================================
# 🔥 THE BULLETPROOF AUDIO EXTRACTOR (HEROKU BAN BYPASS)
# =======================================================
@app.route('/info/<video_id>', methods=['GET'])
def extract_audio_info(video_id):
    bot_sent_key = request.args.get('key') or request.headers.get('Authorization')
    if bot_sent_key:
        user = users_col.find_one({'api_key': bot_sent_key})
        if user:
            users_col.update_one({'api_key': bot_sent_key}, {'$inc': {'play_count': 1}})

    # Heroku IP is banned by YouTube, so we completely bypass yt-dlp 
    # and use 5 public Anti-Bot APIs to get the audio stream!
    PIPED_INSTANCES = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.syncpundit.io",
        "https://api.piped.projectsegfau.lt",
        "https://piped-api.garudalinux.org",
        "https://pipedapi.adminforge.de"
    ]
    
    audio_url = None
    title = f"YouTube Audio {video_id}"
    duration = 0

    for instance in PIPED_INSTANCES:
        try:
            piped_url = f"{instance}/streams/{video_id}"
            res = requests.get(piped_url, timeout=7).json()
            
            if 'audioStreams' in res and len(res['audioStreams']) > 0:
                # Find the best quality audio (usually m4a or webm)
                for stream in res['audioStreams']:
                    if stream.get('mimeType', '').startswith('audio/'):
                        audio_url = stream['url']
                        break
                if not audio_url:
                    audio_url = res['audioStreams'][0]['url']
                    
                title = res.get('title', title)
                duration = res.get('duration', 0)
                break # Success! Break the loop.
        except:
            continue # Try next server if this one fails

    if audio_url:
        # AviaxMusic strictly expects this JSON format from yt-dlp
        fake_ytdlp_info = {
            "id": video_id,
            "title": title,
            "url": audio_url,
            "ext": "m4a",
            "format": "bestaudio",
            "duration": duration,
            "extractor": "youtube"
        }
        resp = make_response(jsonify(fake_ytdlp_info))
        resp.headers['Content-Type'] = 'application/json'
        return resp
    else:
        # If all 5 servers fail (very rare)
        return jsonify({"error": "All bypass servers failed. YouTube block active."}), 500

# =======================================================
# --- SEARCH PROXY ROUTE (Fallback for bot searches)
# =======================================================
@app.route('/youtube/v3/<path:endpoint>', methods=['GET'])
def proxy_youtube(endpoint):
    bot_sent_key = request.args.get('key')
    if bot_sent_key:
        users_col.update_one({'api_key': bot_sent_key}, {'$inc': {'play_count': 1}})

    yt_url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    params = dict(request.args)
    params['key'] = OFFICIAL_YT_KEY
    if 'part' not in params: params['part'] = 'snippet'
    
    try:
        r = requests.get(yt_url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        resp = make_response(jsonify(r.json()))
        resp.headers['Content-Type'] = 'application/json'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- AUTH & DASHBOARD ROUTES ---
@app.route('/')
def index():
    if 'email' in session: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email, pw, cpw = request.form.get('email', '').lower().strip(), request.form.get('password'), request.form.get('confirm_password')
        if pw != cpw: return render_template('register.html', error="Passwords do not match!")
        if users_col.find_one({'email': email}): return render_template('register.html', error="Email exists!")
        key = f"DENKI-{secrets.token_hex(6).upper()}"
        users_col.insert_one({"email": email, "password": generate_password_hash(pw), "username": "Denki_"+''.join(random.choices(string.digits, k=5)), "api_key": key, "balance": 0, "play_count": 0, "max_limit": 150, "plan_name": "Free", "expiry_date": "Lifetime", "last_reset": ist_now().strftime('%Y-%m-%d')})
        session['email'] = email
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, pw = request.form.get('email', '').lower().strip(), request.form.get('password')
        user = users_col.find_one({'email': email})
        if user and check_password_hash(user['password'], pw):
            session['email'] = email
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid!")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session: return redirect(url_for('login'))
    user = sync_user(users_col.find_one({'email': session['email']}))
    return render_template('dashboard.html', user=user, days_left="∞")

@app.route('/api/stats')
def get_stats():
    if 'email' not in session: return jsonify({}), 401
    user = sync_user(users_col.find_one({'email': session['email']}))
    return jsonify({"play_count": user['play_count'], "max_limit": user['max_limit'], "balance": user['balance']})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

