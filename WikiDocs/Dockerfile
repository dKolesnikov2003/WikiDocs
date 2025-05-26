# ---------- Dockerfile ----------
# Минимальный образ, который запускает FastAPI‑backend
# (Фронтенд – статичные файлы, уже лежат в ./frontend и будут раздава‑
# ться самим приложением)
# ---------------------------------

FROM python:3.12-slim AS runtime

# Ускоряем install: отключаем .pyc и убираем cache‑директории
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Создаём рабочую папку внутри контейнера
WORKDIR /app

# Копируем зависимости отдельно – позволит кэшировать слой, пока
# requirements.txt не меняется
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Теперь копируем весь исходный код (backend, frontend и прочие .py)
COPY . .

# Порт можно пробросить в docker‑compose; EXPOSE – лишь инфо
EXPOSE 8000

# CMD: ASGI‑сервер uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
# ---------- Dockerfile ----------
# Минимальный образ, который запускает FastAPI‑backend
# (Фронтенд – статичные файлы, уже лежат в ./frontend и будут раздава‑
# ться самим приложением)
# ---------------------------------

FROM python:3.12-slim AS runtime

# Ускоряем install: отключаем .pyc и убираем cache‑директории
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Создаём рабочую папку внутри контейнера
WORKDIR /app

# Копируем зависимости отдельно – позволит кэшировать слой, пока
# requirements.txt не меняется
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Теперь копируем весь исходный код (backend, frontend и прочие .py)
COPY . .

# Порт можно пробросить в docker‑compose; EXPOSE – лишь инфо
EXPOSE 8000

# CMD: ASGI‑сервер uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
