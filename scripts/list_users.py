#!/usr/bin/env python3
"""List all users in the database."""

from src.users import list_users

def main():
    users = list_users()

    if not users:
        print("No users found in database")
        return

    print(f"Found {len(users)} user(s):\n")
    for user in users:
        print(f"  ID: {user.id}")
        print(f"  Username: {user.username}")
        print(f"  Email: {user.email}")
        print(f"  Role: {user.role}")
        print(f"  Has password: {bool(user.password_hash)}")
        print(f"  Created: {user.created_at}")
        print()

if __name__ == "__main__":
    main()
