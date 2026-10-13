"""Compatibility shim: authentication now lives in `app.core.security`.

Kept so the existing import (`from auth import get_current_user`) in main.py keeps working.
New code should import from app.core.security.
"""

from app.core.security import get_current_user

__all__ = ["get_current_user"]
