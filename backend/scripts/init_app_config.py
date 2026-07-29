"""One-time setup: generate the visitor access code and admin password,
store their hashes in the DB, and print the plaintext values ONCE — they
can't be recovered after this (only re-generated, or changed from the admin
panel once logged in). Usage: python -m scripts.init_app_config
"""

import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.core.auth import hash_secret
from app.db import repository
from app.db.session import dispose_engine, get_session, init_engine


def _generate_code(length: int) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars (0/O, 1/I/L)
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main() -> None:
    settings = get_settings()
    init_engine(settings)
    try:
        async with get_session() as session:
            existing = await repository.get_app_config(session)
            if existing is not None:
                print("app_config already exists — not overwriting. Use the admin panel to change credentials.")
                return

            access_code = _generate_code(8)
            admin_password = _generate_code(16)

            async with get_session() as session:
                await repository.create_app_config(
                    session,
                    access_code_hash=hash_secret(access_code),
                    admin_password_hash=hash_secret(admin_password),
                )

        print("=" * 60)
        print("Whale Sharks — initial credentials (shown once, save them now)")
        print("=" * 60)
        print(f"  Visitor access code: {access_code}")
        print(f"  Admin password:      {admin_password}")
        print("=" * 60)
        print("Both can be changed later from the admin panel (Access Management).")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
