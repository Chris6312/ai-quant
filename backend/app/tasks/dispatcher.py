from __future__ import annotations

from typing import Protocol

from celery import Celery


class CeleryTaskDispatcher(Protocol):
    def send_task(self, name: str, kwargs: dict[str, object]) -> object: ...


class CeleryDispatcher:
    def __init__(self, app: Celery) -> None:
        self._app = app

    def send_task(self, name: str, kwargs: dict[str, object]) -> object:
        return self._app.send_task(name, kwargs=kwargs)