"""main.py
~~~~~~~~~~
Главная точка входа backend‑сервиса.

REST‑энд‑пойнты:
  ─ POST /api/login    – логин по username+password через Wiki.js GraphQL, возвращает JWT.
  ─ GET  /api/tree     – дерево Wiki.js (требует JWT).
  ─ POST /api/upload   – загрузка файла, создание страницы (требует JWT).
+ статика фронта.
"""

from __future__ import annotations

import io
import logging
import os
import re, unicodedata
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
    Request,
    Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.dedoc_client import DedocClient, DedocError
from backend.wikijs_client import WikiJSClient, WikiJSError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# ----------------------------------------------------------------------
# FastAPI + CORS
# ----------------------------------------------------------------------

app = FastAPI(title="Dedoc ▸ Wiki.js uploader", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Singleton Dedoc client
# ----------------------------------------------------------------------

dedoc_client = DedocClient()

def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_name)
    return re.sub(r"-{2,}", "-", slug).strip("-").lower()

def get_token_from_request(request: Request) -> Optional[str]:
    """Достаёт Bearer‑токен из заголовка Authorization (если есть)."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip()

# ----------------------------------------------------------------------
#                          API‑энд‑пойнты
# ----------------------------------------------------------------------

@app.post("/api/login")
async def api_login(data: dict = Body(...)):
    """
    Логин пользователя Wiki.js по username+password.
    Возвращает JWT (или ошибку).
    """
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Требуется username и password")
    try:
        jwt = WikiJSClient.login(
            base_url=os.getenv("WIKIJS_URL", "http://wiki:3000"),
            username=username,
            password=password,
        )
        return {"token": jwt}
    except WikiJSError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

@app.get("/api/tree")
async def api_get_tree(request: Request) -> Any:
    """Вернуть дерево Wiki.js (для меню). Требует валидного токена."""
    jwt = get_token_from_request(request)
    if not jwt:
        raise HTTPException(status_code=401, detail="Необходим Bearer‑токен")
    try:
        wiki_client = WikiJSClient(
            base_url=os.getenv("WIKIJS_URL", "http://wiki:3000"),
            token=jwt,
        )
        tree = wiki_client.get_page_tree()
        return {"tree": tree}
    except WikiJSError as exc:
        logger.error("Wiki.js error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

@app.post("/api/upload")
async def api_upload_file(
    request: Request,
    file: UploadFile = File(..., description="Файл для загрузки"),
    parent_path: str = Form("/", description="Путь каталога, выбранный пользователем"),
) -> Any:
    """Загрузить файл, конвертировать, создать новую страницу (JWT в Authorization)."""
    jwt = get_token_from_request(request)
    if not jwt:
        raise HTTPException(status_code=401, detail="Необходим Bearer‑токен")
    raw_bytes = await file.read()
    try:
        html = dedoc_client.convert_file(io.BytesIO(raw_bytes), file.filename)
    except DedocError as exc:
        logger.error("Dedoc error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    base_name, _ = os.path.splitext(file.filename)
    safe_name = slugify(base_name)
    parent_path = (parent_path or "/").rstrip("/")
    new_path = f"{parent_path}/{safe_name}".replace("//", "/")
    try:
        wiki_client = WikiJSClient(
            base_url=os.getenv("WIKIJS_URL", "http://wiki:3000"),
            token=jwt,
        )
        page = wiki_client.create_page(path=new_path, title=base_name, html_content=html)
    except WikiJSError as exc:
        logger.error("Wiki.js error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "page": page,
            "message": f"Страница успешно создана по пути {page['path']}",
        },
    )

# ------------------------- Статика -------------------------
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")

if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
else:
    logger.warning("frontend dir not found: %s", frontend_dir)

# ------------------------- Запуск --------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=bool(os.getenv("RELOAD", "0") == "1"),
    )
