# Build from repo root:
# docker build -f example-agent/Dockerfile -t example-agent:0.1.0 .

FROM python:3.13-slim

RUN useradd --system --no-create-home --uid 65532 agent

# Install shared library
COPY core-tools-lib/ /tmp/core-tools-lib/
RUN pip install --no-cache-dir /tmp/core-tools-lib/ && rm -rf /tmp/core-tools-lib

# Install agent
WORKDIR /app
COPY example-agent/pyproject.toml ./
COPY example-agent/app/ ./app/
RUN pip install --no-cache-dir .

USER 65532
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
