import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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

    from app.auth import auth_bp
    from app.checker import checker_bp
    from app.routes import bp as main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(checker_bp, url_prefix='/')
    app.register_blueprint(main_bp)

    csrf.exempt(main_bp)
    csrf.exempt(checker_bp)
    csrf.exempt(auth_bp)

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
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify({'status': 'healthy'}), 200
        except Exception:
            return jsonify({'status': 'unhealthy'}), 500

    return app
