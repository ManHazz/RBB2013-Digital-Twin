FROM python:3.11-slim

WORKDIR /app

COPY services/motion_planner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared /app/services/shared
COPY services/motion_planner /app/services/motion_planner

ENV PYTHONPATH=/app

EXPOSE 8020

CMD ["uvicorn", "services.motion_planner.app:app", "--host", "0.0.0.0", "--port", "8020"]
