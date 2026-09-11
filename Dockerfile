FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    MOCK_MODE=true \
    SCHEDULER_ENABLED=true \
    SCHEDULER_TIMEZONE=Asia/Bangkok \
    DATABASE_URL=sqlite:///./data/radar.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "mkdir -p /app/data && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
