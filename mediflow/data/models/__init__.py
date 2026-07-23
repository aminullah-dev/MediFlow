"""ORM model registry.

Importing this package imports every model module so that ``Base.metadata`` is
fully populated before ``create_all`` or Alembic autogenerate runs. Add new
model modules to ``_MODEL_MODULES`` as the schema grows.
"""
from __future__ import annotations

from importlib import import_module

_MODEL_MODULES = (
    "user",
    "audit",
    "clinic",
    "patient",
    "appointment",
    "pharmacy",
    "laboratory",
    "inventory",
    "billing",
    "accounting",
    "hr",
)

for _name in _MODEL_MODULES:
    import_module(f"{__name__}.{_name}")

from mediflow.data.base import Base  # noqa: E402  (re-export after model load)

__all__ = ["Base"]
