from app import db
from app.models import User


def test_register_and_login(client):
    rv = client.post(
        '/auth/register',
        data={'username': 'bob', 'password': 'longenough'},
        follow_redirects=False,
    )
    assert rv.status_code in (302, 303)
    rv = client.post(
        '/auth/login',
        data={'username': 'bob', 'password': 'longenough'},
        follow_redirects=False,
    )
    assert rv.status_code in (302, 303)


def test_login_rejects_locked_user(client, app):
    with app.app_context():
        from datetime import datetime, timedelta
        u = User(username='locked')
        u.set_password('correct')
        u.locked_until = datetime.utcnow() + timedelta(minutes=10)
        db.session.add(u)
        db.session.commit()

    rv = client.post(
        '/auth/login',
        data={'username': 'locked', 'password': 'correct'},
        follow_redirects=True,
    )
    assert 'заблокирован' in rv.get_data(as_text=True)


def test_history_requires_auth(client):
    rv = client.get('/api/check/history')
    assert rv.status_code in (302, 401)


def test_history_returns_user_checks(auth_client):
    rv = auth_client.get('/api/check/history')
    assert rv.status_code == 200
    payload = rv.get_json()
    assert payload['ok'] is True
    assert payload['checks'] == []
