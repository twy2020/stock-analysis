FROM node:22-alpine AS stock-search
ARG STOCK_WEB=0
RUN mkdir -p /opt/stock-search && if [ "$STOCK_WEB" = "1" ]; then npm install --prefix /opt/stock-search ai-search-mcp@0.4.1; fi

FROM node:22-alpine AS stock-socks
ARG STOCK_WEB=0
RUN mkdir -p /opt/stock-socks && if [ "$STOCK_WEB" = "1" ]; then npm install --prefix /opt/stock-socks fetch-socks@1.2.0; fi

FROM python:3.12-slim AS runtime
ARG STOCK_WEB=0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
COPY requirements-stock-web.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -r requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$STOCK_WEB" = "1" ]; then pip install --timeout 120 -r requirements-stock-web.txt; fi
COPY --from=stock-search /opt/stock-search /opt/stock-search
COPY --from=stock-search /usr/local/bin/node /opt/stock-node/node
COPY --from=stock-search /lib /opt/stock-node/lib
COPY --from=stock-search /usr/lib/libstdc++.so.6* /usr/lib/libgcc_s.so.1 /opt/stock-node/lib/
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/stock-browsers
RUN if [ "$STOCK_WEB" = "1" ]; then \
    patchright install --with-deps chromium && chmod -R a+rX /opt/stock-browsers; fi
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY wsgi.py ./
COPY --from=stock-socks /opt/stock-socks /opt/stock-socks
RUN addgroup --system app && adduser --system --ingroup app app && mkdir -p /data && chown -R app:app /data /app
USER app
EXPOSE 8000
# Provider concurrency counters are process-local. One threaded worker keeps
# each configured account limit authoritative for this single-container SaaS.
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --workers 1 --threads 64 --timeout 180 --bind 0.0.0.0:8000 wsgi:app"]
