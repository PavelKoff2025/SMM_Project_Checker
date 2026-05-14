"""End-to-end check that the provider chosen on upload is the one that
actually gets called.

We mock the OpenAI SDK constructor and intercept what base_url / model
arrive at the client. This proves the routing without spending tokens.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import db
from app.checker.llm_client import DeepSeekClient, GrokClient, create_client
from app.models import ProjectCheck, User

_LONG_COMMENT = (
    'Это развёрнутый комментарий длиной более ста двадцати символов. '
    'В нём перечислены сильные стороны раздела и конкретные рекомендации '
    'студенту перед защитой проекта.'
)
_LONG_SUMMARY = (
    'Это общий итог по проекту длиной более двухсот символов, '
    'который содержит развёрнутый главный вывод по презентации. '
    'В целом проект удался, но есть пункты для доработки перед защитой: '
    'в первую очередь это анализ конкурентов и креативы для VK Ads, '
    'а также юзабилити площадок VK, Telegram и Дзен.'
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Disable backoff to keep retry-driven tests fast."""
    monkeypatch.setattr('app.checker.llm_client.time.sleep', lambda *_: None)

_FAKE_LLM_JSON = (
    '{"score": 7, '
    '"criteria": {"structure": 7, "platform_design": 7, '
    '"usp": 7, "competitor_analysis": 7, "vk_ads": 7}, '
    f'"criteria_feedback": {{'
    f'"structure": "{_LONG_COMMENT}", '
    f'"platform_design": "{_LONG_COMMENT}", '
    f'"usp": "{_LONG_COMMENT}", '
    f'"competitor_analysis": "{_LONG_COMMENT}", '
    f'"vk_ads": "{_LONG_COMMENT}"}}, '
    f'"feedback": "{_LONG_SUMMARY}", '
    '"strengths": ["a strong UVP", "well-structured slides"], '
    '"weaknesses": ["thin ER analysis", "few creatives"]}'
)


def _patched_openai(monkeypatch, captured: dict) -> None:
    class FakeChatCompletions:
        def create(self, **kwargs):
            captured['model'] = kwargs.get('model')
            captured['messages'] = kwargs.get('messages')
            captured['response_format'] = kwargs.get('response_format')
            captured['max_tokens'] = kwargs.get('max_tokens')
            msg = MagicMock()
            msg.content = _FAKE_LLM_JSON
            choice = MagicMock()
            choice.message = msg
            response = MagicMock()
            response.choices = [choice]
            return response

    class FakeChat:
        completions = FakeChatCompletions()

    class FakeOpenAI:
        def __init__(self, api_key: str, base_url: str):
            captured['api_key'] = api_key
            captured['base_url'] = base_url
            self.chat = FakeChat()

    monkeypatch.setattr('app.checker.llm_client.OpenAI', FakeOpenAI)


def test_create_client_grok_targets_xai(monkeypatch):
    captured: dict = {}
    _patched_openai(monkeypatch, captured)

    client = create_client('grok', {'GROK_API_KEY': 'xai-test-key'})
    client.analyze_presentation(text='hi', system_prompt='sys')

    assert isinstance(client, GrokClient)
    assert captured['api_key'] == 'xai-test-key'
    assert captured['base_url'] == 'https://api.x.ai/v1'
    assert captured['model'] == GrokClient.DEFAULT_MODEL
    assert captured['response_format'] == {'type': 'json_object'}


def test_create_client_deepseek_targets_deepseek(monkeypatch):
    captured: dict = {}
    _patched_openai(monkeypatch, captured)

    client = create_client('deepseek', {'DEEPSEEK_API_KEY': 'sk-deepseek'})
    client.analyze_presentation(text='hi', system_prompt='sys')

    assert isinstance(client, DeepSeekClient)
    assert captured['api_key'] == 'sk-deepseek'
    assert captured['base_url'] == 'https://api.deepseek.com'
    assert captured['model'] == 'deepseek-chat'


def test_create_client_respects_model_override(monkeypatch):
    captured: dict = {}
    _patched_openai(monkeypatch, captured)

    client = create_client(
        'grok',
        {'GROK_API_KEY': 'xai-test-key', 'GROK_MODEL': 'grok-3-mini'},
    )
    client.analyze_presentation(text='hi', system_prompt='sys')

    assert captured['base_url'] == 'https://api.x.ai/v1'
    assert captured['model'] == 'grok-3-mini'


@pytest.fixture
def configured_app(app):
    app.config['DEEPSEEK_API_KEY'] = 'sk-deepseek'
    app.config['GROK_API_KEY'] = 'xai-key'
    return app


def _seed_check(app, user_id: int, provider: str) -> int:
    import os
    upload_dir = app.config['UPLOAD_FOLDER']
    safe = 'fake.pdf'
    path = os.path.join(upload_dir, safe)
    with open(path, 'wb') as fh:
        fh.write(b'%PDF-1.4\nfake content\n')
    check = ProjectCheck(
        user_id=user_id,
        original_filename='fake.pdf',
        safe_filename=safe,
        status='processing',
        llm_provider=provider,
    )
    db.session.add(check)
    db.session.commit()
    return check.id


def test_run_check_uses_grok_when_check_says_grok(monkeypatch, configured_app):
    """Full service-level check: orchestrator must pick Grok when stored."""
    captured: dict = {}
    _patched_openai(monkeypatch, captured)

    monkeypatch.setattr(
        'app.services.check_service.parse_presentation',
        lambda path, ext: type(
            'Parsed', (),
            {
                'full_text': 'some slide text',
                'slide_texts': ['s1', 's2'],
                'slide_titles': ['t1', 't2'],
                'slide_count': 2,
                'is_empty': False,
            }
        )(),
    )

    user = User(username='charlie')
    user.set_password('p')
    db.session.add(user)
    db.session.commit()

    check_id = _seed_check(configured_app, user.id, 'grok')

    from app.services.check_service import run_check
    run_check(configured_app, check_id)

    assert captured['base_url'] == 'https://api.x.ai/v1'
    assert captured['model'] == GrokClient.DEFAULT_MODEL

    refreshed = db.session.get(ProjectCheck, check_id)
    assert refreshed.status == 'completed'
    assert refreshed.llm_provider == 'grok'


def test_run_check_uses_deepseek_when_check_says_deepseek(monkeypatch, configured_app):
    captured: dict = {}
    _patched_openai(monkeypatch, captured)

    monkeypatch.setattr(
        'app.services.check_service.parse_presentation',
        lambda path, ext: type(
            'Parsed', (),
            {
                'full_text': 'some slide text',
                'slide_texts': ['s1'],
                'slide_titles': ['t1'],
                'slide_count': 1,
                'is_empty': False,
            }
        )(),
    )

    user = User(username='dave')
    user.set_password('p')
    db.session.add(user)
    db.session.commit()

    check_id = _seed_check(configured_app, user.id, 'deepseek')

    from app.services.check_service import run_check
    run_check(configured_app, check_id)

    assert captured['base_url'] == 'https://api.deepseek.com'
    assert captured['model'] == 'deepseek-chat'
