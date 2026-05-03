# Build context: this directory (tar.gz root)
# docker build -t echo-agent:latest .

FROM python:3.13-slim

RUN useradd --system --no-create-home --uid 65532 agent

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

USER 65532
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
