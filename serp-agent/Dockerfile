# Build from repo root:
# docker build -f serp-agent/Dockerfile -t serp-agent:latest .

FROM python:3.13-slim

RUN useradd --system --no-create-home --uid 65532 serp

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install shared library
COPY core-tools-lib/ /tmp/core-tools-lib/
RUN pip install --no-cache-dir /tmp/core-tools-lib/ && rm -rf /tmp/core-tools-lib

# Install agent
WORKDIR /app
COPY serp-agent/pyproject.toml ./
COPY serp-agent/src/ ./src/
COPY serp-agent/app/ ./app/
RUN pip install --no-cache-dir . && \
    playwright install --with-deps chromium && \
    chmod -R 755 /ms-playwright

USER 65532
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
