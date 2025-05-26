"""wikijs_client.py
~~~~~~~~~~~~~~~~~~~
Мини‑клиент для GraphQL‑API **Wiki.js 2.5.307**.

Поддерживает ровно то, что нужно MVP:
* получение дерева страниц (`get_page_tree`)
* создание страницы с HTML‑контентом (`create_page`)
* fallback‑метод `list_pages` для построения дерева вручную

Важно: в версии 2.5.307 мутация `pages.create` принимает **отдельные
аргументы**, а не `CreatePageInput`.  Поэтому метод `create_page` формирует
мутэйшен с отдельными полями.

Конфигурация через переменные окружения (или явные аргументы конструктора):
    WIKIJS_URL   – http://wiki:3000
    WIKIJS_TOKEN – Bearer‑токен с правами «Pages: Read / Create»
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

__all__ = ["WikiJSClient", "WikiJSError"]


class WikiJSError(RuntimeError):
    """Ошибка, возникающая при неправильном ответе Wiki.js."""


class WikiJSClient:
    """Мини‑обёртка для GraphQL Wiki.js (v2.5.307)."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 300) -> None:
        self.base_url = (base_url or os.getenv("WIKIJS_URL", "")).rstrip("/")
        self.endpoint = f"{self.base_url}/graphql"
        self.timeout = timeout
        self.session = requests.Session()
        self.token = token
        # Не требуем токен сразу, можно задать позже!
        self._update_headers()

    def _update_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.clear()
        self.session.headers.update(headers)

    def set_token(self, token: str) -> None:
        self.token = token
        self._update_headers()

    @classmethod
    def login(cls, base_url: str, username: str, password: str, timeout: int = 30) -> str:
        """
        Логин через GraphQL mutation. Возвращает JWT.
        """
        import requests

        endpoint = f"{base_url.rstrip('/')}/graphql"
        payload = {
            "query": """
                mutation Login($username: String!, $password: String!) {
                  authentication {
                    login(
                      username: $username,
                      password: $password,
                      strategy: "local"
                    ) { jwt }
                  }
                }
            """,
            "variables": {"username": username, "password": password},
        }
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            raise WikiJSError("Некорректный ответ от Wiki.js (не JSON)")
        if resp.status_code != 200 or body.get("errors") or not body.get("data"):
            raise WikiJSError(body.get("errors") or resp.text)
        jwt = body["data"]["authentication"]["login"]["jwt"]
        if not jwt:
            raise WikiJSError("Wiki.js не выдал токен")
        return jwt

    # -------------------------------------------------------------
    # Внутренний помощник
    # -------------------------------------------------------------
    def _execute(self, query: str, variables: dict | None = None) -> dict:
        payload = {"query": query, "variables": variables or {}}
        resp = self.session.post(self.endpoint, json=payload, timeout=self.timeout)
        try:
            body = resp.json()
        except ValueError as exc:
            logger.error("Wiki.js вернул не‑JSON: %s", resp.text[:200])
            raise WikiJSError("Некорректный JSON") from exc

        if resp.status_code != 200 or body.get("errors"):
            raise WikiJSError(body.get("errors") or resp.text)
        return body["data"]

    # -------------------------------------------------------------
    # Получение дерева
    # -------------------------------------------------------------
    def get_page_tree(self, root_path: str = "/", locale: str = "ru") -> List[Dict]:
        query = (
            """
            query ($path: String!, $locale: String!) {
              pages { tree(path: $path, locale: $locale) {
                id path title isDirectory
                children { id path title isDirectory }
              }}
            }
            """
        )
        try:
            data = self._execute(query, {"path": root_path, "locale": locale})
            return data["pages"]["tree"]
        except WikiJSError as exc:
            logger.warning("pages.tree не работает, fallback list_pages: %s", exc)
            return self._build_tree_from_paths(self.list_pages())

    # -------------------------------------------------------------
    # Листинг всех страниц
    # -------------------------------------------------------------
    def list_pages(self) -> List[Dict]:
        query = (
            """
            query { pages { list(orderBy: TITLE) { id path title } } }
            """
        )
        data = self._execute(query)
        return data["pages"]["list"]

    @staticmethod
    def _build_tree_from_paths(pages: List[Dict]) -> List[Dict]:
        root: Dict[str, dict] = {}
        for page in pages:
            parts = [p for p in page["path"].strip("/").split("/") if p]
            cursor = root
            for depth, part in enumerate(parts):
                cursor = cursor.setdefault(part, {"__children__": {}, "__meta__": None})
                if depth == len(parts) - 1:
                    cursor["__meta__"] = {
                        "id": page["id"],
                        "path": page["path"],
                        "title": page["title"],
                    }
                cursor = cursor["__children__"]

        def build(node: Dict[str, dict], prefix: str = "") -> List[Dict]:
            tree: List[Dict] = []
            for segment, data in sorted(node.items()):
                children = build(data["__children__"], f"{prefix}/{segment}")
                meta = data["__meta__"] or {"id": None, "path": f"{prefix}/{segment}", "title": segment}
                tree.append({**meta, "children": children})
            return tree

        return build(root)

    # -------------------------------------------------------------
    # Создание страницы
    # -------------------------------------------------------------
    def create_page(
        self,
        *,
        path: str,
        title: str,
        html_content: str,
        locale: str = "ru",
        description: str | None = None,
        tags: Optional[List[str]] = None,
        is_published: bool = True,
        is_private: bool = False,
        editor: str = "code",
    ) -> Dict:
        """Создать страницу и вернуть базовую информацию о ней."""
        mutation = (
            """
            mutation (
              $content: String!,
              $description: String!,
              $editor: String!,
              $isPublished: Boolean!,
              $isPrivate: Boolean!,
              $locale: String!,
              $path: String!,
              $tags: [String]!,
              $title: String!
            ) {
              pages {
                create(
                  content: $content,
                  description: $description,
                  editor: $editor,
                  isPublished: $isPublished,
                  isPrivate: $isPrivate,
                  locale: $locale,
                  path: $path,
                  tags: $tags,
                  title: $title
                ) {
                  responseResult { succeeded message errorCode }
                  page { id path title }
                }
              }
            }
            """
        )
        variables = {
            "content": html_content,
            "description": description or title,
            "editor": editor,
            "isPublished": is_published,
            "isPrivate": is_private,
            "locale": locale,
            "path": path,
            "tags": tags or [],
            "title": title,
        }
        data = self._execute(mutation, variables)
        res = data["pages"]["create"]
        if not res["responseResult"]["succeeded"]:
            raise WikiJSError(res["responseResult"].get("message", "Create failed"))
        return res["page"]


# ------------------------- CLI‑тест --------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = WikiJSClient()
    print("Дерево первых 3 узлов:")
    print(client.get_page_tree()[:3])
