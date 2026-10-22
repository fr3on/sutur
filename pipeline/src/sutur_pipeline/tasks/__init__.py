"""Importing this package registers the built-in tasks."""

from . import build, cast, chunk, cover, draw, lab, narrate, pdf, plan, publish, spec, textscan, vision  # noqa: F401  (imported for their @register side effect)
from .base import Context, Kind, Result, Status, Task
from .registry import DEFAULT, Registry, register

__all__ = ["DEFAULT", "Task", "Context", "Kind", "Registry", "Result", "Status", "register"]
