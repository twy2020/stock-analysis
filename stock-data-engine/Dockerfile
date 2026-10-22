FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STOCK_ENGINE_HOST=0.0.0.0 STOCK_ENGINE_PORT=18310 STOCK_DATA_DIR=/data/datasets
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 120 -r requirements.txt
COPY stock_engine ./stock_engine
RUN addgroup --system app && adduser --system --ingroup app app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 18310
CMD ["python", "-m", "stock_engine"]
