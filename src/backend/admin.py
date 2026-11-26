"""Manage CodexJ admin accounts from the command line.

Usage (from src/, like backend.serve):
    python -m backend.admin list
    python -m backend.admin promote <username>
    python -m backend.admin demote <username>

Admins can open the admin dashboard (/admin) to see user count, per-user
storage, and last login. No API route can grant admin - only this command.
Runs pending migrations first, so it works against a DB the server hasn't
upgraded yet. Safe to run while the server is running; the change applies
on the user's next request.
"""

import argparse
import sys

from backend.database.querying import get_all_users, set_user_admin
from backend.database.structural import run_migrations


def _list() -> int:
    users = get_all_users()
    if not users:
        print("No users.")
        return 0
    for user in users:
        marker = "admin" if user.is_admin else "     "
        print(f"{marker}  {user.username}")
    return 0


def _set(username: str, is_admin: bool) -> int:
    if not set_user_admin(username, is_admin):
        sys.stderr.write(f"No such user: {username}\n")
        return 1
    print(f"{username} is {'now' if is_admin else 'no longer'} an admin.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.admin")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list users, marking admins")
    for name, help_text in (("promote", "grant admin"), ("demote", "revoke admin")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("username")
    args = parser.parse_args(argv)

    run_migrations()
    if args.command == "list":
        return _list()
    return _set(args.username, args.command == "promote")


if __name__ == "__main__":
    sys.exit(main())
