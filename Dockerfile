FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 northstar
COPY --chown=northstar:northstar app ./app
COPY --chown=northstar:northstar sample_documents ./sample_documents
RUN mkdir /app/data && chown northstar:northstar /app/data
USER northstar
ENV DATABASE_PATH=/app/data/northstar.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
