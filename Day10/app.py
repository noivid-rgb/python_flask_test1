import os

from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

    @app.get('/')
    def index():
        return jsonify({
            'service': 'Day 10 Flask deployment demo',
            'status': 'running',
            'environment': os.environ.get('APP_ENV', 'production'),
        })

    @app.get('/healthz')
    def healthz():
        return jsonify({'status': 'ok'}), 200

    @app.get('/readyz')
    def readyz():
        if not app.config['SECRET_KEY']:
            return jsonify({'status': 'not ready', 'reason': 'SECRET_KEY is missing'}), 503
        return jsonify({'status': 'ready'}), 200

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))