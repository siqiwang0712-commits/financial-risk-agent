FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY rules ./rules
COPY config ./config
RUN pip install --no-cache-dir .
RUN addgroup --system finrisk && adduser --system --ingroup finrisk finrisk \
    && chown -R finrisk:finrisk /app
USER finrisk
CMD ["uvicorn","finrisk.api:app","--host","0.0.0.0","--port","8000"]
