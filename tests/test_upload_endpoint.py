"""Smoke test for the upload pipeline.

We monkeypatch `enqueue_check` so the actual LLM call is never made — this
test only verifies HTTP plumbing, validation, and DB row creation.
"""

import io

import pytest

from app.models import ProjectCheck


@pytest.fixture
def deepseek_configured(app):
    app.config['DEEPSEEK_API_KEY'] = 'sk-test'
    return app


@pytest.fixture
def grok_configured(app):
    app.config['GROK_API_KEY'] = 'xai-test'
    return app


@pytest.fixture
def stub_enqueue(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        'app.checker.routes.enqueue_check', lambda cid: calls.append(cid)
    )
    return calls


def test_upload_rejects_missing_file(auth_client, deepseek_configured):
    rv = auth_client.post('/api/check/upload', data={})
    assert rv.status_code == 400


def test_upload_rejects_wrong_extension(auth_client, deepseek_configured):
    rv = auth_client.post(
        '/api/check/upload',
        data={'file': (io.BytesIO(b'irrelevant'), 'malware.exe')},
        content_type='multipart/form-data',
    )
    assert rv.status_code == 400


def test_upload_rejects_pdf_without_magic(auth_client, deepseek_configured):
    rv = auth_client.post(
        '/api/check/upload',
        data={'file': (io.BytesIO(b'fake'), 'doc.pdf')},
        content_type='multipart/form-data',
    )
    assert rv.status_code == 400


def test_upload_rejects_when_provider_not_configured(
    auth_client, app, stub_enqueue, monkeypatch
):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.delenv('GROK_API_KEY', raising=False)
    app.config['DEEPSEEK_API_KEY'] = ''
    app.config['GROK_API_KEY'] = ''
    rv = auth_client.post(
        '/api/check/upload',
        data={'file': (io.BytesIO(b'%PDF-1.4 hi'), 'doc.pdf')},
        content_type='multipart/form-data',
    )
    assert rv.status_code == 400
    assert 'не настроен' in rv.get_json()['error']
    assert stub_enqueue == []


def test_upload_accepts_valid_pdf_with_default_provider(
    auth_client, app, deepseek_configured, stub_enqueue
):
    rv = auth_client.post(
        '/api/check/upload',
        data={'file': (io.BytesIO(b'%PDF-1.4 hi'), 'doc.pdf')},
        content_type='multipart/form-data',
    )
    assert rv.status_code == 201
    payload = rv.get_json()
    assert payload['status'] == 'processing'
    assert payload['provider'] == 'deepseek'
    assert stub_enqueue == [payload['check_id']]

    with app.app_context():
        check = ProjectCheck.query.get(payload['check_id'])
        assert check is not None
        assert check.llm_provider == 'deepseek'


def test_upload_persists_grok_provider_choice(
    auth_client, app, grok_configured, stub_enqueue
):
    rv = auth_client.post(
        '/api/check/upload',
        data={
            'file': (io.BytesIO(b'%PDF-1.4 hi'), 'doc.pdf'),
            'provider': 'grok',
        },
        content_type='multipart/form-data',
    )
    assert rv.status_code == 201
    payload = rv.get_json()
    assert payload['provider'] == 'grok'

    with app.app_context():
        check = ProjectCheck.query.get(payload['check_id'])
        assert check.llm_provider == 'grok'


def test_upload_unknown_provider_falls_back_to_default(
    auth_client, app, deepseek_configured, stub_enqueue
):
    rv = auth_client.post(
        '/api/check/upload',
        data={
            'file': (io.BytesIO(b'%PDF-1.4 hi'), 'doc.pdf'),
            'provider': 'mistral',
        },
        content_type='multipart/form-data',
    )
    assert rv.status_code == 201
    assert rv.get_json()['provider'] == 'deepseek'


def test_providers_endpoint_lists_configuration_state(
    auth_client, app, deepseek_configured, monkeypatch
):
    monkeypatch.delenv('GROK_API_KEY', raising=False)
    app.config['GROK_API_KEY'] = ''
    rv = auth_client.get('/api/providers')
    assert rv.status_code == 200
    payload = rv.get_json()
    assert payload['default'] == 'deepseek'
    by_key = {item['key']: item for item in payload['providers']}
    assert by_key['deepseek']['configured'] is True
    assert by_key['grok']['configured'] is False
