"""Compatibility shim: authentication now lives in `app.core.security`.

Kept so existing imports (`from auth import get_current_user`) in main.py and
create_user.py keep working. New code should import from app.core.security.
"""

from app.core.security import get_current_user, hash_password, verify_password

__all__ = ["get_current_user", "hash_password", "verify_password"]
