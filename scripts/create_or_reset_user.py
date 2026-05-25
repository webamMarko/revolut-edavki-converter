#!/usr/bin/env python3
"""Create user marko or reset their password if they already exist."""

import secrets
import string
from src.users import (
    get_users_db,
    get_user_by_email,
    change_password,
    hash_password,
)

def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def main():
    conn = get_users_db()

    email = "marko.ambrozic90@gmail.com"
    username = "marko"

    # Check if user exists by email
    user = get_user_by_email(email, conn)

    # Generate new password
    new_password = generate_secure_password(16)

    if user:
        # User exists, reset password
        print(f"Found existing user: {user.username} ({user.email})")
        success = change_password(user.id, new_password, conn)
        if success:
            print(f"✅ Password reset successful")
        else:
            print("ERROR: Failed to update password")
            conn.close()
            return 1
    else:
        # User doesn't exist, create them
        print(f"User not found, creating new user...")
        pw_hash = hash_password(new_password)
        try:
            conn.execute(
                """INSERT INTO users (username, email, password_hash, role)
                   VALUES (?, ?, ?, 'premium')""",
                (username, email, pw_hash),
            )
            conn.commit()
            print(f"✅ User created successfully")
        except Exception as e:
            print(f"ERROR: Failed to create user: {e}")
            conn.close()
            return 1

    conn.close()

    print(f"\n👤 Username: {username}")
    print(f"📧 Email: {email}")
    print(f"🔑 New password: {new_password}")
    print("\nPlease save this password securely.")
    return 0

if __name__ == "__main__":
    exit(main())
