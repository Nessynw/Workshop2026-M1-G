FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements-api.txt
COPY api.py security.py api_access.py index.html login.html container_entrypoint.py ./
ENTRYPOINT ["python", "container_entrypoint.py"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
