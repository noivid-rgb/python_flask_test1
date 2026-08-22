import os
from functools import wraps

from flask import Flask, jsonify, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'day5-development-secret')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    messages = db.relationship('GuestbookMessage', backref='author', lazy=True)


class GuestbookMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin123'))
        db.session.add(admin)
        db.session.commit()
        db.session.add(GuestbookMessage(
            content='歡迎來到 Day 5 RESTful API 留言板！',
            user_id=admin.id,
        ))
        db.session.commit()


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None
        if user is None:
            return jsonify({
                'error': 'Unauthorized',
                'message': '請先登入才可以發表留言。',
            }), 401
        return view(user, *args, **kwargs)

    return wrapped


def message_to_dict(message):
    return {
        'id': message.id,
        'username': message.author.username,
        'content': message.content,
    }


@app.get('/')
def index():
    return render_template('guestbook.html', username=session.get('username'))


@app.post('/api/register')
def register_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Bad Request', 'message': 'Request body 必須是 JSON。'}), 400

    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({'error': 'Bad Request', 'message': 'username 同 password 必須是文字。'}), 400

    username = username.strip()
    if not username or not password:
        return jsonify({'error': 'Bad Request', 'message': '帳號同密碼不可為空。'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Conflict', 'message': '此帳號已經存在。'}), 409

    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return jsonify({'id': user.id, 'username': user.username}), 201


@app.post('/api/login')
def login_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Bad Request', 'message': 'Request body 必須是 JSON。'}), 400

    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first() if isinstance(username, str) else None
    if user is None or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Unauthorized', 'message': '帳號或密碼錯誤。'}), 401

    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'username': user.username}), 200


@app.post('/api/logout')
def logout_api():
    session.clear()
    return jsonify({'message': '已登出。'}), 200


@app.get('/api/messages')
def get_messages_api():
    messages = GuestbookMessage.query.order_by(GuestbookMessage.id.desc()).all()
    return jsonify([message_to_dict(message) for message in messages]), 200


@app.post('/api/messages')
@api_login_required
def create_message_api(current_user):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('content'), str):
        return jsonify({'error': 'Bad Request', 'message': '請以 JSON 傳送 content 文字欄位。'}), 400

    content = data['content'].strip()
    if not content:
        return jsonify({'error': 'Bad Request', 'message': '留言內容不可為空。'}), 400

    message = GuestbookMessage(content=content, user_id=current_user.id)
    db.session.add(message)
    db.session.commit()
    return jsonify(message_to_dict(message)), 201


if __name__ == '__main__':
    app.run(debug=True)