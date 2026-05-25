#!/usr/bin/env python3
"""Reset password for user marko and output the new password."""

import secrets
import string
from src.users import get_users_db, change_password

def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def main():
    conn = get_users_db()

    # Look up user marko
    row = conn.execute(
        "SELECT id, username, email FROM users WHERE username = ?",
        ("marko",)
    ).fetchone()

    if not row:
        print("ERROR: User 'marko' not found in database")
        conn.close()
        return 1

    user_id = row["id"]
    username = row["username"]
    email = row["email"]

    # Generate new password
    new_password = generate_secure_password(16)

    # Update password
    success = change_password(user_id, new_password, conn)

    conn.close()

    if success:
        print(f"✅ Password reset successful for user: {username}")
        print(f"   Email: {email}")
        print(f"   User ID: {user_id}")
        print(f"\n🔑 New password: {new_password}")
        print("\nPlease save this password securely.")
        return 0
    else:
        print("ERROR: Failed to update password")
        return 1

if __name__ == "__main__":
    exit(main())
