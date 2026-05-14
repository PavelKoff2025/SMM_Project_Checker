import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

from config import config_by_name

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'


def create_app(config_name: str = 'development') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.queue import init_queue
    init_queue(app)

    from app.auth import auth_bp
    from app.checker import checker_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(checker_bp)

    # JSON API endpoints are used by XHR without csrf_token; auth forms keep CSRF.
    csrf.exempt(checker_bp)

    if config_name != 'development':
        app.config.update(
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
        )

    if not app.debug:
        handler = RotatingFileHandler(
            os.path.join(os.path.dirname(app.instance_path), 'app.log'),
            maxBytes=10485760, backupCount=10,
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)

    @app.route('/api/health')
    def health():
        components = {'db': 'ok', 'queue': 'disabled'}
        status_code = 200
        try:
            db.session.execute(text('SELECT 1'))
        except Exception:
            components['db'] = 'fail'
            status_code = 500

        from app.queue import get_redis
        redis_client = get_redis()
        if redis_client is not None:
            try:
                redis_client.ping()
                components['queue'] = 'ok'
            except Exception:
                components['queue'] = 'fail'
                status_code = 500

        return jsonify({
            'status': 'healthy' if status_code == 200 else 'unhealthy',
            'components': components,
        }), status_code

    return app
