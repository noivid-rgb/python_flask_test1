import datetime as dt
import os
import time
from functools import wraps

import jwt
from celery import Celery
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from pydantic import BaseModel, Field, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'day9-development-secret-key-change-me')
app.config['JWT_EXPIRES_MINUTES'] = 30
app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

celery = Celery(__name__, broker=app.config['CELERY_BROKER_URL'], backend=app.config['CELERY_RESULT_BACKEND'])
celery.conf.update(task_track_started=True, result_expires=3600)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class TaskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    delay_seconds: int = Field(default=5, ge=0, le=30)


with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin123')))
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


@celery.task(bind=True, name='day9.process_ai_task')
def process_ai_task(self, question, delay_seconds=5):
    """Simulate a slow AI/email operation without blocking Flask."""
    self.update_state(state='PROGRESS', meta={'step': 'processing', 'percent': 10})
    time.sleep(delay_seconds)
    self.update_state(state='PROGRESS', meta={'step': 'building response', 'percent': 90})
    return {
        'answer': f'（Celery mock AI）已完成問題處理：{question}',
        'question': question,
    }


@app.get('/')
def index():
    return render_template('tasks.html')


@app.post('/api/login')
def login_api():
    data = request.get_json(silent=True)
    username = data.get('username') if isinstance(data, dict) else None
    password = data.get('password') if isinstance(data, dict) else None
    user = User.query.filter_by(username=username).first() if isinstance(username, str) else None
    if user is None or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Unauthorized', 'message': '帳號或密碼錯誤。'}), 401
    return jsonify({'token': create_token(user), 'username': user.username}), 200


@app.post('/api/tasks')
@token_required
def create_task_api(current_user):
    del current_user
    try:
        task_request = TaskRequest.model_validate(request.get_json(silent=True))
    except ValidationError as error:
        return jsonify({'error': 'Validation Error', 'details': error.errors()}), 422
    task = process_ai_task.delay(task_request.question, task_request.delay_seconds)
    return jsonify({
        'task_id': task.id,
        'status': 'PENDING',
        'status_url': f'/api/tasks/{task.id}',
    }), 202


@app.get('/api/tasks/<task_id>')
@token_required
def task_status_api(current_user, task_id):
    del current_user
    result = celery.AsyncResult(task_id)
    response = {'task_id': task_id, 'status': result.status}
    if result.status == 'SUCCESS':
        response['result'] = result.result
    elif result.status == 'FAILURE':
        response['error'] = 'Task failed'
    elif isinstance(result.info, dict):
        response['progress'] = result.info
    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)