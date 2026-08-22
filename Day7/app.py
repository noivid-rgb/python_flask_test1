import datetime as dt
import os
from functools import wraps

import jwt
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'day7-development-secret-key-change-me')
app.config['JWT_EXPIRES_MINUTES'] = 30
app.config['LLM_PROVIDER'] = os.environ.get('LLM_PROVIDER', 'mock').lower()
app.config['LLM_MODEL'] = os.environ.get('LLM_MODEL', 'llama-3.1-8b-instant')
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


class MessageSchema(Schema):
    id = fields.Int(required=True)
    username = fields.Str(required=True)
    content = fields.Str(required=True)


message_schema = MessageSchema(many=True)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    prompt: str = Field(min_length=1, max_length=2000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    model: str
    provider: str
    answer: str


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin123'))
        db.session.add(admin)
        db.session.commit()
        db.session.add(GuestbookMessage(
            content='歡迎來到 Day 7：數據驗證與 LLM API 練習！',
            user_id=admin.id,
        ))
        db.session.commit()


def create_token(user):
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({
        'sub': str(user.id),
        'username': user.username,
        'iat': now,
        'exp': now + dt.timedelta(minutes=app.config['JWT_EXPIRES_MINUTES']),
    }, app.config['SECRET_KEY'], algorithm='HS256')


def token_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        scheme, _, token = request.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not token:
            return jsonify({'error': 'Unauthorized', 'message': '請提供 Bearer token。'}), 401
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = db.session.get(User, int(payload['sub']))
        except (KeyError, TypeError, ValueError, jwt.InvalidTokenError):
            return jsonify({'error': 'Unauthorized', 'message': 'Token 無效或已過期。'}), 401
        if user is None:
            return jsonify({'error': 'Unauthorized', 'message': 'Token 所屬用戶不存在。'}), 401
        return view(user, *args, **kwargs)

    return wrapped


def validation_error_response(error):
    return jsonify({
        'error': 'Validation Error',
        'details': error.errors(),
    }), 422


def call_llm(chat_request):
    provider = app.config['LLM_PROVIDER']
    model = app.config['LLM_MODEL']

    if provider == 'mock':
        return f'（Mock 回應）你嘅問題係：{chat_request.prompt}', provider, model

    if provider == 'groq':
        api_key = os.environ.get('GROQ_API_KEY')
        if not api_key:
            raise RuntimeError('LLM_PROVIDER=groq 時必須設定 GROQ_API_KEY。')
        from groq import Groq
        client = Groq(api_key=api_key)
        result = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': chat_request.prompt}],
            temperature=chat_request.temperature,
        )
        return result.choices[0].message.content, provider, model

    if provider == 'gemini':
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('LLM_PROVIDER=gemini 時必須設定 GEMINI_API_KEY。')
        from google import genai
        client = genai.Client(api_key=api_key)
        result = client.models.generate_content(
            model=model,
            contents=chat_request.prompt,
            config={'temperature': chat_request.temperature},
        )
        return result.text, provider, model

    raise RuntimeError('LLM_PROVIDER 必須是 mock、groq 或 gemini。')


@app.get('/')
def index():
    return render_template('guestbook.html')


@app.post('/api/register')
def register_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('username'), str) or not isinstance(data.get('password'), str):
        return jsonify({'error': 'Bad Request', 'message': 'username 同 password 必須是文字。'}), 400
    username = data['username'].strip()
    password = data['password']
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
    username = data.get('username') if isinstance(data, dict) else None
    password = data.get('password') if isinstance(data, dict) else None
    user = User.query.filter_by(username=username).first() if isinstance(username, str) else None
    if user is None or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Unauthorized', 'message': '帳號或密碼錯誤。'}), 401
    return jsonify({'token': create_token(user), 'token_type': 'Bearer', 'username': user.username}), 200


@app.get('/api/messages')
def get_messages_api():
    messages = GuestbookMessage.query.order_by(GuestbookMessage.id.desc()).all()
    return jsonify(message_schema.dump(messages)), 200


@app.post('/api/messages')
@token_required
def create_message_api(current_user):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('content'), str) or not data['content'].strip():
        return jsonify({'error': 'Bad Request', 'message': 'content 必須是非空文字。'}), 400
    message = GuestbookMessage(content=data['content'].strip(), user_id=current_user.id)
    db.session.add(message)
    db.session.commit()
    return jsonify(MessageSchema().dump(message)), 201


@app.post('/api/chat')
@token_required
def chat_api(current_user):
    del current_user
    try:
        chat_request = ChatRequest.model_validate(request.get_json(silent=True))
    except ValidationError as error:
        return validation_error_response(error)
    try:
        answer, provider, model = call_llm(chat_request)
        response = ChatResponse(model=model, provider=provider, answer=answer)
        return jsonify(response.model_dump()), 200
    except RuntimeError as error:
        return jsonify({'error': 'Configuration Error', 'message': str(error)}), 503
    except Exception:
        app.logger.exception('LLM provider request failed')
        return jsonify({'error': 'Bad Gateway', 'message': 'LLM provider 暫時無法回應。'}), 502


if __name__ == '__main__':
    app.run(debug=True)