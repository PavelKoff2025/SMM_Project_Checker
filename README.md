# SMM Project Checker

Автоматизированная система проверки студенческих итоговых проектов по курсу «Взаимодействие с социальными медиа». Анализирует презентации (PDF/PPTX) через LLM (DeepSeek или Grok xAI — на выбор перед каждой проверкой), оценивает структуру, оформление площадок, УТП, анализ конкурентов и VK Ads.

## Возможности

- Загрузка PDF и PPTX презентаций (до 32 МБ)
- Извлечение текста через pdfplumber / PyPDF2 + OCR fallback / python-pptx
- Проверка соответствия шаблону: 10 логических блоков (не привязаны к номерам слайдов)
- Оценка по 5 критериям (0–10):
  - Структура презентации
  - Оформление площадок (VK / Telegram / Дзен)
  - УТП, выгоды, ЦА
  - Анализ конкурентов (ER)
  - VK Ads кампания
- Генерация отчёта: TXT, Markdown, PDF (ReportLab)
- Письмо преподавателя студентам
- История проверок для каждого пользователя
- Выбор LLM (DeepSeek или Grok) для каждой проверки

## Стек

- **Backend**: Python 3.11+, Flask 3.x, SQLAlchemy 2.0
- **Auth**: Flask-Login (username + password)
- **LLM**: DeepSeek и Grok (xAI) на выбор; OpenAI-совместимый SDK, Pydantic-валидация ответа
- **Очередь**: Redis + RQ (fallback на потоки в dev без Redis)
- **Frontend**: Bootstrap 5, Jinja2, Bootstrap Icons
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **ORM**: Flask-Migrate (Alembic)
- **Deploy**: Docker + docker-compose, Gunicorn
- **Качество кода**: ruff, pytest, GitHub Actions

## Быстрый старт

```bash
git clone https://github.com/PavelKoff2025/SMM_Project_Checker
cd SMM_Project_Checker

# Создать .env из примера
cp .env.example .env
# Заполнить SECRET_KEY и как минимум один LLM-ключ:
#   DEEPSEEK_API_KEY и/или GROK_API_KEY

# Установка зависимостей
pip install -r requirements.txt

# Миграция БД
flask db upgrade

# Запуск (dev, порт 8080)
export FLASK_PORT=8080
python3 run.py
```

## Docker

```bash
# Заполнить .env, затем:
docker compose up -d
```

## Тестовый пользователь

```
логин: student
пароль: 123456
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `SECRET_KEY` | Ключ для подписи сессий | обязателен в production |
| `DATABASE_URL` | URL базы данных | `sqlite:///smm_checker.db` |
| `DEEPSEEK_API_KEY` | API ключ DeepSeek | — |
| `DEEPSEEK_MODEL` | Модель DeepSeek | `deepseek-chat` |
| `GROK_API_KEY` | API ключ Grok (xAI) | — |
| `GROK_MODEL` | Модель Grok | `grok-4-1-fast-reasoning` |
| `FLASK_ENV` | Окружение | `development` |
| `FLASK_PORT` | Порт сервера | `5000` |
| `UPLOAD_FOLDER` | Папка загрузок | `./uploads` |
| `REDIS_URL` | URL Redis для очереди RQ | пусто → fallback на потоки |
| `RATELIMIT_STORAGE_URI` | Бэкенд для rate limiter | `memory://` |

## Разработка

```bash
# зависимости разработчика
pip install -r requirements-dev.txt

# линтер
ruff check .

# тесты
pytest
```

CI (`.github/workflows/ci.yml`) выполняет `ruff check` и `pytest` на каждый push/PR.

## Безопасность

Перед деплоем в production:

1. Установите `SECRET_KEY` через переменную окружения (генерация: `python3 -c "import secrets; print(secrets.token_hex(32))"`)
2. Настройте HTTPS через reverse proxy (nginx / Caddy)
3. Смените пароль PostgreSQL в `docker-compose.yml`
4. Ограничьте доступ к `/api/health` при необходимости
5. Рассмотрите добавление CAPTCHA на регистрацию
6. `RATELIMIT_STORAGE_URI` в production указывает на тот же Redis, что и `REDIS_URL` (отдельная БД, например `redis://redis:6379/1`)
