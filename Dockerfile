FROM python:3.12-slim

RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /bin/false appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appgroup . .

RUN mkdir -p uploads && chown appuser:appgroup uploads

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 5000

CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "180", "--keepalive", "5"]
