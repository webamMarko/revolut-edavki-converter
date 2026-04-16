#!/usr/bin/env python3
"""CLI helper: create or bootstrap admin accounts.

Usage:
  # Print a PBKDF2 hash of a password (for manual DB operations):
  python scripts/hash_password.py hash <password>

  # Bootstrap the first admin account (no-op if one already exists):
  python scripts/hash_password.py bootstrap <email> <password>

  # Create a premium user and print their invite link:
  python scripts/hash_password.py invite <email>
"""

import os
import sys

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import users as u


def cmd_hash(args):
    if len(args) != 1:
        print("Usage: hash_password.py hash <password>", file=sys.stderr)
        sys.exit(1)
    print(u.hash_password(args[0]))


def cmd_bootstrap(args):
    if len(args) != 2:
        print("Usage: hash_password.py bootstrap <email> <password>", file=sys.stderr)
        sys.exit(1)
    email, password = args
    admin = u.ensure_bootstrap_admin(email, password)
    print(f"Admin ready: {admin.username} <{admin.email}> (id={admin.id})")


def cmd_invite(args):
    if len(args) != 1:
        print("Usage: hash_password.py invite <email>", file=sys.stderr)
        sys.exit(1)
    email = args[0]
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8080")
    user, raw_token = u.create_user(email, role="premium")
    invite_url = f"{base_url}/invite/{raw_token}"
    print(f"Created user: {user.username} <{user.email}>")
    print(f"Invite URL:   {invite_url}")


COMMANDS = {
    "hash": cmd_hash,
    "bootstrap": cmd_bootstrap,
    "invite": cmd_invite,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
