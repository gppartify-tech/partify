"""Command line helpers.

    python -m app.cli init                     # create/update the tables + load the catalog, admin, demo data
    python -m app.cli create-admin --email you@example.com --password secret123
"""
import argparse
import json
import logging
import subprocess
import sys

from app.database import session_scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="run the database migrations and fill an empty database")
    admin = sub.add_parser("create-admin", help="create an admin account (or make a user admin)")
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", required=True)
    admin.add_argument("--username", default="admin")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "init":
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        from app.seed import seed

        with session_scope() as db:
            print(json.dumps(seed(db), indent=2))
    elif args.cmd == "create-admin":
        from app.seed import create_admin

        with session_scope() as db:
            user = create_admin(db, args.email, args.password, args.username)
            print(f"admin ready: {user.username} <{user.email}>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
