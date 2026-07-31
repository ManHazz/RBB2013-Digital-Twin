FROM python:3.11-slim
WORKDIR /app

COPY services/telemetry/requirements.txt services/telemetry/requirements.txt
RUN pip install --no-cache-dir -r services/telemetry/requirements.txt

COPY services/shared services/shared
COPY services/telemetry/app.py services/telemetry/app.py

ENV PYTHONPATH=/app
CMD ["python", "services/telemetry/app.py"]