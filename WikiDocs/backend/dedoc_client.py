"""dedoc_client.py
~~~~~~~~~~~~~~~~~
Небольшой клиент для контейнера **Dedoc**,
который уже запущен на порту 1231 и принимает файлы для конвертации в
HTML.


Основные задачи клиента:
1. Отправить файл в Dedoc (через REST `/upload`).
2. Забрать HTML из ответа.
3. Очистить его двумя регулярными выражениями (требование из ТЗ).
4. Вернуть «чистый» HTML или бросить понятное исключение, если что‑то
   пошло не так.

Настройка через переменные окружения (никаких хардкодов):
    * ``DEDOC_URL`` – полный URL до энд‑пойнта upload,
      по умолчанию ``http://dedoc:1231/upload``.

Зависимости (backend/requirements.txt):
    requests>=2.31.0
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO, Optional

import requests


class DedocError(RuntimeError):
    """Бросается, если Dedoc вернул ошибку или неожиданный ответ."""


class DedocClient:
    """Мини‑обёртка над REST API Dedoc."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 600):
        # Если переменная окружения не задана, берём дефолт для docker‑compose
        self.url = base_url or os.getenv("DEDOC_URL", "http://dedoc:1231/upload")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Публичный метод, которым пользуется FastAPI‑роут `/api/upload`
    # ------------------------------------------------------------------

    def convert_file(
        self,
        file_obj: BinaryIO,
        filename: str | Path,
        *,
        document_type: str = "other",
        language: str = "rus",
        return_format: str = "html",
    ) -> str:
        """Отправляет файл в Dedoc и возвращает **очищенный** HTML.

        :param file_obj: открытый файловый объект (BinaryIO)
        :param filename: имя файла – просто передаём Dedoc‑у
        :raises DedocError: при HTTP‑ошибке или если Dedoc не вернул HTML
        """
        # 1) Формируем multipart‑запрос
        files = {"file": (Path(filename).name, file_obj)}
        data = {
            "document_type": document_type,
            "language": language,
            "return_format": return_format,
        }

        try:
            resp = requests.post(self.url, files=files, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            raise DedocError(f"Не удалось подключиться к Dedoc: {exc}") from exc

        # Проверяем HTTP‑код; Dedoc обычные ошибки отдаёт 4xx/5xx
        if resp.status_code != 200:
            raise DedocError(f"Dedoc ответил кодом {resp.status_code}: {resp.text[:200]}")

        html = resp.text
        if not html.lstrip().startswith("<"):
            # Dedoc вернул JSON с ошибкой? Попытаемся показать.
            raise DedocError(f"Dedoc вернул неожиданный ответ: {html[:200]}")

        # 2) Чистим HTML ровно так, как указано в ТЗ ------------------
        html = re.sub(r"<sub>\s*id\s*=.*?</sub>", "", html, flags=re.DOTALL)
        html = re.sub(
            r"(<center><small><b>)Page\b(.*?</b></small></center>)",
            r"\\1Страница\\2",
            html,
        )

        return html


# ---------------------------------------------------------------------
# Небольшой manual‑тест: ``python dedoc_client.py sample.docx``
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python dedoc_client.py /path/to/file")
        sys.exit(1)

    test_path = Path(sys.argv[1])
    client = DedocClient()
    with test_path.open("rb") as fp:
        cleaned_html = client.convert_file(fp, test_path.name)

    # Просто распечатаем первые 500 символов, чтобы убедиться, что вернулся HTML
    print(cleaned_html[:500])
