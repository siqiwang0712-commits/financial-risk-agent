FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY rules ./rules
COPY config ./config
RUN pip install --no-cache-dir .
CMD ["uvicorn","finrisk.api:app","--host","0.0.0.0","--port","8000"]
