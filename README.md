# SMM Project Checker

Автоматизированная система проверки студенческих итоговых проектов по курсу «Взаимодействие с социальными медиа». Анализирует презентации (PDF/PPTX) через DeepSeek API, оценивает структуру, оформление площадок, УТП, анализ конкурентов и VK Ads.

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

## Стек

- **Backend**: Python 3.11+, Flask 3.x, SQLAlchemy 2.0
- **Auth**: Flask-Login (username + password)
- **LLM**: DeepSeek API (openai SDK)
- **Frontend**: Bootstrap 5, Jinja2, Bootstrap Icons
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **ORM**: Flask-Migrate (Alembic)
- **Deploy**: Docker + docker-compose, Gunicorn

## Быстрый старт

```bash
git clone https://github.com/PavelKoff2025/SMM_Project_Checker
cd SMM_Project_Checker

# Создать .env из примера
cp .env.example .env
# Заполнить DEEPSEEK_API_KEY и SECRET_KEY

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
| `FLASK_ENV` | Окружение | `development` |
| `FLASK_PORT` | Порт сервера | `5000` |
| `UPLOAD_FOLDER` | Папка загрузок | `./uploads` |

## Безопасность

Перед деплоем в production:

1. Установите `SECRET_KEY` через переменную окружения (генерация: `python3 -c "import secrets; print(secrets.token_hex(32))"`)
2. Настройте HTTPS через reverse proxy (nginx / Caddy)
3. Смените пароль PostgreSQL в `docker-compose.yml`
4. Ограничьте доступ к `/api/health` при необходимости
5. Рассмотрите добавление CAPTCHA на регистрацию
6. Настройте rate limit storage backend (Redis) через `RATELIMIT_STORAGE_URL`
