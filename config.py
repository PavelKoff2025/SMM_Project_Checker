import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

    GROK_API_KEY = os.environ.get('GROK_API_KEY', '')
    GROK_MODEL = os.environ.get('GROK_MODEL', 'grok-4-1-fast-reasoning')

    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'),
    )
    ALLOWED_EXTENSIONS = {'pdf', 'pptx'}
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024

    REDIS_URL = os.environ.get('REDIS_URL', '')
    RATELIMIT_STORAGE_URI = os.environ.get(
        'RATELIMIT_STORAGE_URI', os.environ.get('RATELIMIT_STORAGE_URL', '')
    ) or 'memory://'


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///smm_checker.db'
    )


class ProductionConfig(Config):
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError('SECRET_KEY environment variable is required in production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://smm_user:smm_pass@db:5432/smm_checker',
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}
