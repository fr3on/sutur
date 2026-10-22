"""Tasks by name. `@register` adds an task class to the default registry; tests build their own."""

from __future__ import annotations

from collections.abc import Iterator

from ..errors import GraphError
from .base import Task


class Registry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        if task.name in self._tasks:
            raise GraphError(f"two tasks are called {task.name!r}")
        self._tasks[task.name] = task

    def get(self, name: str) -> Task:
        try:
            return self._tasks[name]
        except KeyError:
            raise GraphError(f"unknown stage {name!r}; known: {', '.join(sorted(self._tasks)) or 'none'}") from None

    def __iter__(self) -> Iterator[Task]:
        return iter(self._tasks.values())

    def __contains__(self, name: str) -> bool:
        return name in self._tasks


DEFAULT = Registry()


def register[A: type[Task]](cls: A) -> A:
    """Class decorator: `DEFAULT.add(cls())`."""
    DEFAULT.add(cls())
    return cls
