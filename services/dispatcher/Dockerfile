FROM python:3.11-slim

WORKDIR /app

COPY services/dispatcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/dispatcher /app/services/dispatcher

ENV PYTHONPATH=/app

EXPOSE 8030
EXPOSE 5556

CMD ["uvicorn", "services.dispatcher.app:app", "--host", "0.0.0.0", "--port", "8030"]
