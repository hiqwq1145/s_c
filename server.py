from flask import Flask, request, jsonify, session
import time
import hashlib
from datetime import datetime, timezone
import os
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)
app.secret_key = 'change_this_to_random_string_12345'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)

def init_db():
    if not DATABASE_URL:
        print("警告：未找到DATABASE_URL")
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            sender TEXT NOT NULL,
            time TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    if count == 0:
        boy_hash = hashlib.sha256("0708".encode()).hexdigest()
        girl_hash = hashlib.sha256("0213".encode()).hexdigest()
        cur.execute("INSERT INTO users (password_hash, role) VALUES (%s, %s)", (boy_hash, 'boy'))
        cur.execute("INSERT INTO users (password_hash, role) VALUES (%s, %s)", (girl_hash, 'girl'))
        print("已创建账户：我的密码=0708，她的密码=0213")
    conn.commit()
    cur.close()
    conn.close()

init_db()

def check_password(pwd):
    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE password_hash = %s", (pwd_hash,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        return result['role']
    return None

@app.route('/')
def index():
    return open('chat.html').read()

@app.route('/auth', methods=['POST'])
def auth():
    pwd = request.json.get('password')
    role = check_password(pwd)
    if role:
        token = hashlib.sha256(f"{pwd}{time.time()}".encode()).hexdigest()
        session['auth'] = token
        session['role'] = role
        session['expire'] = time.time() + 1800
        return jsonify({'status': 'ok', 'role': role})
    return jsonify({'status': 'error'}), 401

@app.route('/check_auth')
def check_auth():
    if 'auth' in session and time.time() < session.get('expire', 0):
        return jsonify({'valid': True, 'role': session.get('role')})
    return jsonify({'valid': False})

@app.route('/messages', methods=['GET', 'POST'])
def handle_messages():
    if not ('auth' in session and time.time() < session.get('expire', 0)):
        return jsonify({'error': 'unauthorized'}), 401
    
    if request.method == 'GET':
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT text, sender, time, created_at FROM messages ORDER BY created_at ASC LIMIT 500")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        messages = []
        for r in rows:
            # 优先使用完整时间：如果 time 字段已经是 ISO 格式（包含日期），则用它，否则用 created_at
            time_raw = r['time']
            created_at = r['created_at']
            # 判断 time_raw 是否为完整日期时间（至少包含 YYYY-MM-DD 格式）
            if time_raw and len(time_raw) >= 10 and '-' in time_raw:
                full_time = time_raw
            else:
                # 使用 created_at 并转为 ISO 字符串
                full_time = created_at.isoformat() if created_at else datetime.now(timezone.utc).isoformat()
            
            messages.append({
                'text': r['text'],
                'sender': r['sender'],
                'full_time': full_time
            })
        return jsonify(messages)
    
    elif request.method == 'POST':
        msg = request.json.get('text', '').strip()
        if msg:
            conn = get_db()
            cur = conn.cursor()
            # 存储完整 ISO 时间字符串
            now_iso = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO messages (text, sender, time) VALUES (%s, %s, %s)",
                (msg, session['role'], now_iso)
            )
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
