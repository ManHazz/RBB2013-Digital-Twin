FROM python:3.11-slim

WORKDIR /app

COPY services/actuation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/actuation /app/services/actuation

ENV PYTHONPATH=/app

EXPOSE 8040

CMD ["uvicorn", "services.actuation.app:app", "--host", "0.0.0.0", "--port", "8040"]