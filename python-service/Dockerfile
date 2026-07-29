FROM python:3.12-slim
# Matches platform-n8n/docker/templates/Dockerfile.python-sidecar

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY}

WORKDIR /app

COPY python-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY python-service/ .
COPY prompts/ /app/prompts/
COPY sql/migrations/ /app/sql/migrations/

EXPOSE 8001

CMD ["opentelemetry-instrument", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
