import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# ===== 資料庫設定 =====
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== 定義資料表模型 =====
class GuestbookMessage(db.Model):
    __tablename__ = 'guestbook_messages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)

# ===== 初始化資料庫並寫入預設資料 =====
# 確保資料表存在，如果為空則塞入初始資料
with app.app_context():
    db.create_all()
    if not GuestbookMessage.query.first():
        msg1 = GuestbookMessage(name="Admin", content="歡迎來到 Day 3 升級版資料庫留言板！")
        msg2 = GuestbookMessage(name="Peter", content="現在所有留言都會永久儲存在 SQLite 內喇！")
        db.session.add_all([msg1, msg2])
        db.session.commit()

# ===== 路由設定 =====
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        sender_name = request.form.get('username')
        sender_msg = request.form.get('message')
        
        if sender_name and sender_msg:
            # 【核心修改】不使用 list.append，改用 ORM 語法寫入資料庫
            new_record = GuestbookMessage(name=sender_name, content=sender_msg)
            db.session.add(new_record)
            db.session.commit() # 記得要 commit 才會儲存！
            
        return redirect(url_for('index'))
        
    # 【核心修改】從資料庫讀取所有留言，按 id 倒序排列（最新留言喺最頂）
    messages_from_db = GuestbookMessage.query.order_by(GuestbookMessage.id.desc()).all()
    return render_template('guestbook.html', messages=messages_from_db)

if __name__ == '__main__':
    app.run(debug=True)
