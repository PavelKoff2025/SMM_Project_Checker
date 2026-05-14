import pytest
from pydantic import ValidationError

from app.checker.llm_schema import EXPECTED_CRITERIA, LLMReport

_LONG = (
    'Развёрнутый комментарий на 120+ символов. '
    'Что сделано хорошо, что упущено, и конкретная рекомендация для студента. '
    'Ссылается на содержимое презентации.'
)
_SUMMARY = (
    'Это общий итог по проекту длиной более двухсот символов. '
    'Проект в целом отвечает требованиям курса, но есть ряд моментов, '
    'на которые стоит обратить внимание перед защитой: усилить визуал '
    'на площадках и расширить анализ конкурентов с подробными цифрами.'
)


def _valid_payload(**overrides):
    base = {
        'score': 7.5,
        'criteria': {
            'structure': 8,
            'platform_design': 7,
            'usp': 6,
            'competitor_analysis': 9,
            'vk_ads': 7,
        },
        'criteria_feedback': {
            'structure': _LONG,
            'platform_design': _LONG,
            'usp': _LONG,
            'competitor_analysis': _LONG,
            'vk_ads': _LONG,
        },
        'feedback': _SUMMARY,
        'strengths': ['clear structure', 'strong USP positioning'],
        'weaknesses': ['weak vk_ads creatives', 'shallow competitor analysis'],
    }
    base.update(overrides)
    return base


def test_valid_payload_round_trip():
    report = LLMReport.model_validate(_valid_payload())
    out = report.to_normalized_dict()
    assert set(out.keys()) == {
        'score', 'criteria', 'criteria_feedback', 'feedback', 'strengths', 'weaknesses'
    }
    assert set(out['criteria'].keys()) == set(EXPECTED_CRITERIA)
    assert set(out['criteria_feedback'].keys()) == set(EXPECTED_CRITERIA)
    assert out['score'] == 7.5
    assert len(out['feedback']) >= 200


def test_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        LLMReport.model_validate(_valid_payload(score=11))


def test_rejects_missing_criterion():
    payload = _valid_payload()
    payload['criteria'].pop('vk_ads')
    with pytest.raises(ValidationError):
        LLMReport.model_validate(payload)


def test_rejects_missing_criteria_feedback():
    payload = _valid_payload()
    payload.pop('criteria_feedback')
    with pytest.raises(ValidationError):
        LLMReport.model_validate(payload)


def test_accepts_short_comments_but_marks_terse():
    """Short comments are now accepted; the schema flags terseness instead."""
    payload = _valid_payload()
    payload['criteria_feedback']['usp'] = 'too short'
    report = LLMReport.model_validate(payload)
    assert report.is_too_terse() is True


def test_accepts_short_summary_but_marks_terse():
    payload = _valid_payload(feedback='one short sentence.')
    report = LLMReport.model_validate(payload)
    assert report.is_too_terse() is True


def test_accepts_single_strength_but_marks_terse():
    payload = _valid_payload(strengths=['only one'])
    report = LLMReport.model_validate(payload)
    assert report.is_too_terse() is True


def test_full_payload_is_not_terse():
    report = LLMReport.model_validate(_valid_payload())
    assert report.is_too_terse() is False


def test_drops_empty_items_in_strengths():
    payload = _valid_payload(strengths=['a', '', None, 'b'])
    report = LLMReport.model_validate(payload)
    assert report.strengths == ['a', 'b']
