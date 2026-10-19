FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ITG_WEB_DIR=/app/web PORT=8000 ITG_ORCHESTRATOR=maf ITG_MEMORY_PATH=/tmp/itg_viewer_memory.json
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir ".[azure,agents,mcp]"
RUN useradd -m appuser
USER appuser
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "uvicorn insidethegame.server:app --host 0.0.0.0 --port ${PORT}"]
