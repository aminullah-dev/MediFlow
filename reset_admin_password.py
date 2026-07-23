r"""Admin password recovery utility.

Resets the ``admin`` account to a known password, clears the force-change flag
and any lockout. Run it when the initial temporary password is lost.

Usage (from the project folder, with the app CLOSED):
    .\.venv-win\Scripts\python.exe reset_admin_password.py [new_password]

If no password is given it defaults to "mediflow2026". Change it in the app
afterwards (Users & Roles, or the change-password prompt).
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from mediflow.core.config import Config
from mediflow.core.security import hash_password, verify_password
from mediflow.data.database import Database

USERNAME = "admin"
DEFAULT_PASSWORD = "mediflow2026"


def main() -> int:
    new_password = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PASSWORD
    if len(new_password) < 8:
        print("Password must be at least 8 characters.")
        return 1

    config = Config.bootstrap()
    print(f"Database: {config.database_url}")
    db = Database(config.database_url)
    try:
        password_hash = hash_password(new_password)
        with db.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "UPDATE users SET password_hash = :h, must_change_password = 0, "
                    "failed_login_count = 0, locked_until = NULL WHERE username = :u"
                ),
                {"h": password_hash, "u": USERNAME},
            ).rowcount
        if rows == 0:
            print(f"No user named '{USERNAME}' was found.")
            return 1
        with db.engine.connect() as conn:
            stored = conn.execute(
                text("SELECT password_hash FROM users WHERE username = :u"),
                {"u": USERNAME},
            ).scalar_one()
        ok = verify_password(new_password, stored)
    finally:
        db.dispose()

    print()
    print("  Reset complete." if ok else "  Reset FAILED verification.")
    print(f"    username: {USERNAME}")
    print(f"    password: {new_password}")
    print()
    print("  Open MediFlow and sign in. Change this password afterwards.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
