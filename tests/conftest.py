import os

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('FLASK_ENV', 'testing')


@pytest.fixture
def app(tmp_path):
    from app import create_app, db
    upload_dir = tmp_path / 'uploads'
    upload_dir.mkdir()
    application = create_app('testing')
    application.config.update(
        UPLOAD_FOLDER=str(upload_dir),
        WTF_CSRF_ENABLED=False,
        TESTING=True,
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    from app import db
    from app.models import User
    u = User(username='alice')
    u.set_password('correct horse')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def auth_client(client, user):
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True
    return client
