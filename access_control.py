"""Small, testable role checks for the Streamlit club dashboard.

The actual passwords belong in Streamlit Secrets, never in git. Each login
is tied to the current password using an HMAC (without keeping the password
itself in session state), so rotating a password invalidates existing logins.
"""
from __future__ import annotations

import hashlib
import hmac

ROLES = ('admin', 'viewer')


def config_error(admin_password: str, viewer_password: str) -> str | None:
    """Fail closed if either role has no distinct, sufficiently long password."""
    if not admin_password or not viewer_password:
        return 'Bitte ADMIN_PASSWORD und VIEWER_PASSWORD in den Streamlit-Secrets hinterlegen.'
    if len(admin_password) < 12 or len(viewer_password) < 12:
        return 'Beide Passwörter müssen mindestens 12 Zeichen haben.'
    if hmac.compare_digest(admin_password.encode('utf-8'), viewer_password.encode('utf-8')):
        return 'ADMIN_PASSWORD und VIEWER_PASSWORD müssen unterschiedlich sein.'
    return None


def authenticate(entered: str, admin_password: str, viewer_password: str) -> str | None:
    """Return role for a matching password; do not expose which is checked first."""
    if config_error(admin_password, viewer_password) is not None or not entered:
        return None
    admin_match = hmac.compare_digest(entered.encode('utf-8'), admin_password.encode('utf-8'))
    viewer_match = hmac.compare_digest(entered.encode('utf-8'), viewer_password.encode('utf-8'))
    if admin_match:
        return 'admin'
    if viewer_match:
        return 'viewer'
    return None


def session_proof(role: str, admin_password: str, viewer_password: str) -> str:
    """Sign an authorization marker; stale sessions fail after secret rotation."""
    if role not in ROLES:
        raise ValueError('Ungültige Rolle.')
    secret = admin_password if role == 'admin' else viewer_password
    return hmac.new(secret.encode('utf-8'), f'a-team-role-v1:{role}'.encode(), hashlib.sha256).hexdigest()


def session_valid(role: str | None, proof: str | None,
                  admin_password: str, viewer_password: str) -> bool:
    if role not in ROLES or not isinstance(proof, str):
        return False
    if config_error(admin_password, viewer_password) is not None:
        return False
    return hmac.compare_digest(proof, session_proof(role, admin_password, viewer_password))


def can_edit(role: str | None) -> bool:
    return role == 'admin'
