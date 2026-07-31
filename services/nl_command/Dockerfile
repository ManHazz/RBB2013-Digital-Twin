FROM python:3.11-slim

WORKDIR /app

COPY services/nl_command/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/nl_command /app/services/nl_command

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.nl_command.app:app", "--host", "0.0.0.0", "--port", "8010"]