"""Strict schema for LLM responses.

The system prompt instructs the model to return exactly this shape, and we
ask the API for a JSON object (response_format). Validation is done with
Pydantic; if validation fails, the call is retried once with a corrective
follow-up. There is no heuristic key matching anymore.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

EXPECTED_CRITERIA = (
    'structure',
    'platform_design',
    'usp',
    'competitor_analysis',
    'vk_ads',
)

# Soft minimum length — we accept any non-trivial answer, then ask for an
# expansion in a follow-up call when the content is shorter than desired.
# Hard minimums here would force the whole check to error out, which is a
# worse UX than a slightly terse but otherwise correct report.
_MIN_PER_CRITERION_CHARS = 1
_MIN_SUMMARY_CHARS = 1

# Soft targets used by the client to decide whether to request an expansion.
DESIRED_PER_CRITERION_CHARS = 120
DESIRED_SUMMARY_CHARS = 200


class CriteriaScores(BaseModel):
    structure: float = Field(ge=0, le=10)
    platform_design: float = Field(ge=0, le=10)
    usp: float = Field(ge=0, le=10)
    competitor_analysis: float = Field(ge=0, le=10)
    vk_ads: float = Field(ge=0, le=10)

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in EXPECTED_CRITERIA}


class CriteriaFeedback(BaseModel):
    """Per-criterion narrative; ideally a 2–3 sentence comment."""

    structure: str = Field(min_length=_MIN_PER_CRITERION_CHARS)
    platform_design: str = Field(min_length=_MIN_PER_CRITERION_CHARS)
    usp: str = Field(min_length=_MIN_PER_CRITERION_CHARS)
    competitor_analysis: str = Field(min_length=_MIN_PER_CRITERION_CHARS)
    vk_ads: str = Field(min_length=_MIN_PER_CRITERION_CHARS)

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in EXPECTED_CRITERIA}


class LLMReport(BaseModel):
    score: float = Field(ge=0, le=10)
    criteria: CriteriaScores
    criteria_feedback: CriteriaFeedback
    feedback: str = Field(min_length=_MIN_SUMMARY_CHARS)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)

    def is_too_terse(self) -> bool:
        if len(self.feedback) < DESIRED_SUMMARY_CHARS:
            return True
        per = self.criteria_feedback.as_dict()
        if any(len(v) < DESIRED_PER_CRITERION_CHARS for v in per.values()):
            return True
        if len(self.strengths) < 2 or len(self.weaknesses) < 2:
            return True
        return False

    @field_validator('strengths', 'weaknesses', mode='before')
    @classmethod
    def _coerce_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if item is not None and str(item).strip()
            ]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def to_normalized_dict(self) -> dict[str, Any]:
        return {
            'score': self.score,
            'criteria': self.criteria.as_dict(),
            'criteria_feedback': self.criteria_feedback.as_dict(),
            'feedback': self.feedback,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
        }


__all__ = [
    'LLMReport',
    'CriteriaScores',
    'CriteriaFeedback',
    'EXPECTED_CRITERIA',
    'ValidationError',
]
