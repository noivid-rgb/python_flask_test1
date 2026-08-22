import os
import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

app = Flask(__name__)

# ===== 系統安全與資料庫配置 =====
# 實務上應從環境變數讀取：os.environ.get('SECRET_KEY')
app.config['SECRET_KEY'] = 'erb_flask_jwt_super_secret_key_day6'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== 定義資料表模型 =====

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    messages = db.relationship('GuestbookMessage', backref='author', lazy=True)

class GuestbookMessage(db.Model):
    __tablename__ = 'guestbook_messages'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# ===== 初始化資料庫與預設帳號 =====
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('admin123')
        admin_user = User(username='admin', password_hash=hashed_pw)
        db.session.add(admin_user)
        db.session.commit()
        
        msg = GuestbookMessage(content='歡迎來到 Day 6 JWT 無狀態認證展示留言板！請嘗試在下方進行 AJAX JWT 認證！', user_id=admin_user.id)
        db.session.add(msg)
        db.session.commit()

# ===== 自訂：JWT API 認證裝飾器 (Decorator) =====

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # 從 HTTP Headers 中提取 Authorization 欄位
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            # 標準格式：Bearer <token_string>
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({"error": "Unauthorized", "message": "缺少 API 認證 Token 憑證，請先登入！"}), 401
            
        try:
            # 解碼與驗證 Token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({"error": "Unauthorized", "message": "Token 所屬之用戶不存在！"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Unauthorized", "message": "登入憑證已過期，請重新登入！"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Unauthorized", "message": "無效的 Token 憑證，拒絕存取！"}), 401
            
        # 將驗證過後的用戶對象傳遞給下一個路由函數
        return f(current_user, *args, **kwargs)
        
    return decorated


# ===== 1. 傳統模板渲染路由 (僅供首頁載入) =====
# 喺你的主程式 app.py 中新增此路由，以便瀏覽器能正常訪問該頁面
@app.route('/auth', methods=['GET'])
def auth_page():
    return render_template('auth.html')

@app.route('/', methods=['GET'])
def index():
    # 預先加載留言列表以供首次渲染
    messages_from_db = GuestbookMessage.query.order_by(GuestbookMessage.id.desc()).all()
    return render_template('guestbook.html', messages=messages_from_db)


# ===== 2. Day 6 全新：JWT 無狀態認證 API 端點 =====

# 【API 註冊端點】
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Bad Request", "message": "請提供完整的用戶名與密碼！"}), 400
        
    username = data.get('username').strip()
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Bad Request", "message": "用戶名或密碼不能為空！"}), 400
        
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": "Conflict", "message": "此用戶名已被註冊！"}), 409
        
    hashed_pw = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"status": "success", "message": "註冊成功！請使用該帳號登入。"}), 201


# 【API 登入端點 - 簽發 JWT Token】
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Bad Request", "message": "請輸入用戶名與密碼！"}), 400
        
    username = data.get('username').strip()
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and check_password_hash(user.password_hash, password):
        # 帳密驗證成功，簽發 JWT！
        payload = {
            "user_id": user.id,
            "username": user.username,
            # 設定 Token 於 30 分鐘後失效
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }
        token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            "status": "success",
            "message": "認證成功！已簽發安全 Token。",
            "token": token,
            "username": user.username
        }), 200
    else:
        return jsonify({"error": "Unauthorized", "message": "用戶名或密碼錯誤！"}), 401


# 【獲取所有留言 API (不需 Token，唯讀)】
@app.route('/api/messages', methods=['GET'])
def get_messages_api():
    messages_from_db = GuestbookMessage.query.order_by(GuestbookMessage.id.desc()).all()
    api_list = []
    for msg in messages_from_db:
        api_list.append({
            "id": msg.id,
            "username": msg.author.username,
            "content": msg.content
        })
    return jsonify(api_list), 200


# 【發表留言 API (受 JWT 裝飾器 `@token_required` 保護)】
@app.route('/api/messages', methods=['POST'])
@token_required
def create_message_api(current_user): # 接收裝飾器傳來的 current_user
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({"error": "Bad Request", "message": "傳送的數據不完整！"}), 400
        
    sender_msg = data.get('content').strip()
    if not sender_msg:
        return jsonify({"error": "Bad Request", "message": "留言內容不能為空！"}), 400
        
    # 寫入資料庫，關聯當前 JWT 驗證通過的用戶
    new_record = GuestbookMessage(content=sender_msg, user_id=current_user.id)
    db.session.add(new_record)
    db.session.commit()
    
    response_data = {
        "id": new_record.id,
        "username": current_user.username,
        "content": new_record.content
    }
    return jsonify(response_data), 201


if __name__ == '__main__':
    app.run(debug=True)