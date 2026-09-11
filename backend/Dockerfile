FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY backend ./backend
COPY rules ./rules
COPY config ./config
RUN python -m pip install --no-cache-dir pip==25.2 \
    && python -m pip install --no-cache-dir -c requirements.lock .
RUN addgroup --system finrisk && adduser --system --ingroup finrisk finrisk \
    && chown -R finrisk:finrisk /app
USER finrisk
CMD ["uvicorn","finrisk.api:app","--host","0.0.0.0","--port","8000"]
