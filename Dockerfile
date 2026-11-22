FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOT_MODE=webhook

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-bot.txt ./requirements-bot.txt
RUN pip install --no-cache-dir -r requirements-bot.txt

COPY telegram_bot.py kbc_processor.py menu.json ./

CMD ["python", "telegram_bot.py"]
