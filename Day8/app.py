import datetime as dt
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import wraps

import jwt
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from pydantic import BaseModel, Field, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'day8-development-secret-key-change-me')
app.config['JWT_EXPIRES_MINUTES'] = 30
app.config['LLM_PROVIDER'] = os.environ.get('LLM_PROVIDER', 'mock').lower()
app.config['LLM_MODEL'] = os.environ.get('LLM_MODEL', 'llama-3.1-8b-instant')
app.config['RAG_MIN_SCORE'] = float(os.environ.get('RAG_MIN_SCORE', '0.08'))
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: int
    source: str
    text: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=5)


class TfidfVectorStore:
    """A small, dependency-free vector store for teaching purposes."""

    token_pattern = re.compile(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]')

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.documents = [self._tokens(chunk.text) for chunk in self.chunks]
        self.document_frequency = Counter(
            token for tokens in self.documents for token in set(tokens)
        )
        self.vocabulary = sorted(self.document_frequency)
        self.vectors = [self._vectorize(tokens) for tokens in self.documents]

    @classmethod
    def _tokens(cls, text):
        return [token.lower() for token in cls.token_pattern.findall(text)]

    def _vectorize(self, tokens):
        counts = Counter(tokens)
        document_count = len(self.documents)
        vector = {}
        for token, count in counts.items():
            inverse_document_frequency = math.log(
                (1 + document_count) / (1 + self.document_frequency[token])
            ) + 1
            vector[token] = (count / len(tokens)) * inverse_document_frequency
        return vector

    @staticmethod
    def _cosine(left, right):
        denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
            sum(value * value for value in right.values())
        )
        if not denominator:
            return 0.0
        numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
        return numerator / denominator

    def search(self, query, top_k=3):
        query_tokens = self._tokens(query)
        query_vector = self._vectorize(query_tokens) if query_tokens else {}
        scored = [
            (self._cosine(query_vector, vector), chunk)
            for vector, chunk in zip(self.vectors, self.chunks)
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(round(score, 4), chunk) for score, chunk in scored[:top_k] if score > 0]


def split_into_chunks(text, source, max_chars=180):
    sentences = [part.strip() for part in re.split(r'(?<=[。！？.!?])', text) if part.strip()]
    chunks = []
    current = ''
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = ''
        current += sentence
    if current:
        chunks.append(current)
    return [DocumentChunk(index, source, chunk) for index, chunk in enumerate(chunks)]


KNOWLEDGE_DOCUMENTS = {
    'company_faq.md': (
        '退款政策：一般商品在收貨後七日內可以申請退貨，商品必須保持完整。'
        '申請退款需要提供訂單編號，客服會在收到退貨後五個工作天內處理。'
        '客服服務時間：星期一至星期五上午九時至下午六時，週末及公眾假期休息。'
    ),
    'shipping.md': (
        '香港本地訂單一般會在一至三個工作天內送達。偏遠地區或天氣情況可能造成延誤。'
        '訂單出貨後，系統會以電郵發送追蹤編號。若超過五個工作天仍未收到，請聯絡客服。'
    ),
    'account.md': (
        '忘記密碼時，請在登入頁選擇重設密碼，並按電郵指示完成驗證。'
        '帳戶資料只可以由帳戶持有人修改，客服不會透過電話索取完整密碼。'
    ),
}
ALL_CHUNKS = [
    chunk
    for source, text in KNOWLEDGE_DOCUMENTS.items()
    for chunk in split_into_chunks(text, source)
]
VECTOR_STORE = TfidfVectorStore(ALL_CHUNKS)


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


def call_llm(prompt):
    provider = app.config['LLM_PROVIDER']
    model = app.config['LLM_MODEL']
    if provider == 'mock':
        context = prompt.split('參考資料：', 1)[-1].split('使用者問題：', 1)[0].strip()
        return f'（Mock RAG 回應）我只根據以下參考資料回答：\n{context}', provider, model
    if provider == 'groq':
        api_key = os.environ.get('GROQ_API_KEY')
        if not api_key:
            raise RuntimeError('LLM_PROVIDER=groq 時必須設定 GROQ_API_KEY。')
        from groq import Groq
        result = Groq(api_key=api_key).chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
        )
        return result.choices[0].message.content, provider, model
    if provider == 'gemini':
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('LLM_PROVIDER=gemini 時必須設定 GEMINI_API_KEY。')
        from google import genai
        result = genai.Client(api_key=api_key).models.generate_content(
            model=model, contents=prompt, config={'temperature': 0.1}
        )
        return result.text, provider, model
    raise RuntimeError('LLM_PROVIDER 必須是 mock、groq 或 gemini。')


@app.get('/')
def index():
    return render_template('qa.html')


@app.post('/api/login')
def login_api():
    data = request.get_json(silent=True)
    username = data.get('username') if isinstance(data, dict) else None
    password = data.get('password') if isinstance(data, dict) else None
    user = User.query.filter_by(username=username).first() if isinstance(username, str) else None
    if user is None or not isinstance(password, str) or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Unauthorized', 'message': '帳號或密碼錯誤。'}), 401
    return jsonify({'token': create_token(user), 'username': user.username}), 200


@app.get('/api/knowledge')
def knowledge_api():
    return jsonify([{'source': chunk.source, 'chunk_id': chunk.chunk_id, 'text': chunk.text} for chunk in ALL_CHUNKS])


@app.post('/api/ask')
@token_required
def ask_api(current_user):
    del current_user
    try:
        query = QueryRequest.model_validate(request.get_json(silent=True))
    except ValidationError as error:
        return jsonify({'error': 'Validation Error', 'details': error.errors()}), 422

    results = [
        result for result in VECTOR_STORE.search(query.question, query.top_k)
        if result[0] >= app.config['RAG_MIN_SCORE']
    ]
    sources = [
        {'source': chunk.source, 'chunk_id': chunk.chunk_id, 'score': score, 'text': chunk.text}
        for score, chunk in results
    ]
    context = '\n'.join(f'[{item["source"]}#{item["chunk_id"]}] {item["text"]}' for item in sources)
    prompt = (
        '你是一個企業客服。只可以根據參考資料回答；如果資料沒有答案，請明確回答「資料不足」。'
        f'\n參考資料：\n{context or "（沒有找到相關資料）"}'
        f'\n使用者問題：{query.question}'
    )
    try:
        answer, provider, model = call_llm(prompt)
    except RuntimeError as error:
        return jsonify({'error': 'Configuration Error', 'message': str(error)}), 503
    except Exception:
        app.logger.exception('RAG LLM request failed')
        return jsonify({'error': 'Bad Gateway', 'message': 'LLM provider 暫時無法回應。'}), 502
    return jsonify({'answer': answer, 'provider': provider, 'model': model, 'sources': sources}), 200


if __name__ == '__main__':
    app.run(debug=True)