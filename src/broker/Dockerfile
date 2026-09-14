FROM python:3.12-slim

WORKDIR /app

COPY app.py ./app.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
