FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt
COPY api.py index.html ./

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]