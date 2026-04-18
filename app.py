import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Intha Catch-all route bot anuppura yella request-aiyum trap pannidum!
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def catch_all(path):
    print("========================================")
    print(f"🔥 BOT REQUESTED EXACT PATH: /{path}")
    print(f"🔥 BOT SENT PARAMETERS: {request.args}")
    print("========================================")
    
    # Bot-ku thevaiyillatha data anuppi dummy response tharoom
    return jsonify({"success": False, "error": "Denki Trap Activated"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

