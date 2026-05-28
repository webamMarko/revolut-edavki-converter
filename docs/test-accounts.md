# Test Accounts

Pre-created accounts for manual testing and development. All accounts exist in the deployed database at `data/_system/users.db`.

> ⚠️ Non-production only. Passwords are intentionally simple.

## Accounts by Role

| Username | Role | Password | Notes |
|---|---|---|---|
| `marko` | admin | *(personal — not shared)* | Primary owner account |
| `admin_test` | admin | `admin123` | Full admin access — user management, all data |
| `cofounder_demo` | cofounder | `cofounder123` | Co-founder tier — same as admin plus co-founder pricing features |
| `premium_user` | premium | `premium123` | Standard paid user — own portfolio DB |
| `guest_demo` | guest | `guest123` | Read-only demo access — sees `_demo` portfolio only |

## Role Capabilities Summary

| Role | Own Portfolio | Admin Panel | Co-founder Features |
|---|---|---|---|
| `guest` | ❌ (demo only) | ❌ | ❌ |
| `premium` | ✅ | ❌ | ❌ |
| `admin` | ✅ | ✅ | ❌ |
| `cofounder` | ✅ | ✅ | ✅ |

## Re-creating Accounts

If the database is reset, run this snippet from the project root (server path):

```bash
cd /home/homeassistant/revolut-edavki-converter
REVOLUT_DATA_DIR=/home/homeassistant/revolut-edavki-converter/data python3 - << 'EOF'
import sys, os
sys.path.insert(0, '.')
from src.users import get_users_db, hash_password

accounts = [
    ('guest_demo',     'guest_demo@example.com',     'guest',      'guest123'),
    ('premium_user',   'premium_user@example.com',   'premium',    'premium123'),
    ('admin_test',     'admin_test@example.com',     'admin',      'admin123'),
    ('cofounder_demo', 'cofounder_demo@example.com', 'cofounder',  'cofounder123'),
]

conn = get_users_db()
for username, email, role, password in accounts:
    existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    pw_hash = hash_password(password)
    if existing:
        conn.execute('UPDATE users SET password_hash=?, role=?, invite_token=NULL WHERE username=?', (pw_hash, role, username))
    else:
        conn.execute('INSERT INTO users (username, email, password_hash, role) VALUES (?,?,?,?)', (username, email, pw_hash, role))
    conn.commit()
    print(f'  {username} ({role}) — ok')
conn.close()
EOF
```

## App URL

`http://192.168.4.213:8080` (or whichever port Docker maps to)
