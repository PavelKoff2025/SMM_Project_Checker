import json
import re
import time
from openai import OpenAI


EXPECTED_KEYS = {'score', 'criteria', 'feedback', 'strengths', 'weaknesses'}
EXPECTED_CRITERIA = {'structure', 'platform_design', 'usp', 'competitor_analysis', 'vk_ads'}


def _sanitize_user_text(text: str) -> str:
    text = re.sub(r'(?i)(ignore|override|forget|disregard).{0,50}(instruction|prompt|rule|system)', '[REDACTED]', text)
    return text[:12000]


def _validate_llm_output(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError('LLM response is not a dict')
    if not isinstance(data.get('score'), (int, float)):
        raise ValueError('LLM response missing/invalid score')
    criteria = data.get('criteria', {})
    if not isinstance(criteria, dict):
        raise ValueError('LLM response criteria is not a dict')
    for key in EXPECTED_CRITERIA:
        if not isinstance(criteria.get(key), (int, float)):
            criteria[key] = 0
    if not isinstance(data.get('feedback'), str):
        data['feedback'] = ''
    data['strengths'] = [str(s) for s in (data.get('strengths') or [])]
    data['weaknesses'] = [str(w) for w in (data.get('weaknesses') or [])]
    data['score'] = max(0.0, min(10.0, float(data['score'])))
    for k in EXPECTED_CRITERIA:
        criteria[k] = max(0.0, min(10.0, float(criteria.get(k, 0))))
    return data


class DeepSeekClient:

    def __init__(self, api_key: str, model: str = 'deepseek-chat'):
        self.client = OpenAI(
            api_key=api_key,
            base_url='https://api.deepseek.com',
        )
        self.model = model
        self.max_retries = 3
        self.timeout = 120

    def _build_messages(self, text: str, system_prompt: str) -> list:
        return [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': text},
        ]

    def _clean_response(self, content: str) -> str:
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        return content.strip()

    def analyze_presentation(self, text: str, system_prompt: str = '') -> dict:
        user_text = _sanitize_user_text(text)
        messages = self._build_messages(user_text, system_prompt)
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content
                cleaned = self._clean_response(content)
                data = json.loads(cleaned)
                return _validate_llm_output(data)

            except (json.JSONDecodeError, KeyError, ValueError, Exception) as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    time.sleep(wait)

        raise RuntimeError(
            f'Failed after {self.max_retries} retries. Last error: {last_error}'
        )
