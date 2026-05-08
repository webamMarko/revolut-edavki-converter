# Deploy Skill

Deploy the portfolio app to the production server.

## Prerequisites

- `sshpass` installed locally (`brew install sshpass`)
- Server password available (set `REMOTE_PASS` env var or enter interactively)

## Server Details

- **Host:** `homeassistant@192.168.4.213`
- **Remote path:** `/home/homeassistant/revolut-edavki-converter/`
- **App URL:** `http://192.168.4.213:8081`
- **Container:** `portfolio` (Docker, `--restart unless-stopped`)
- **Ports:** Host 8081 → Container 8080

## Deploy Commands

### Full deploy (code + databases)

```bash
REMOTE_PASS='<password>' ./scripts/deploy.sh
```

### Code-only deploy (skip database copy)

```bash
REMOTE_PASS='<password>' ./scripts/deploy.sh --skip-db
```

## What the deploy does

1. Creates tarball of project (excludes `.git`, `data/`, `venv/`, `.env`)
2. Uploads via `scp` to `homeassistant@192.168.4.213`
3. Extracts into `/home/homeassistant/revolut-edavki-converter/`
4. Copies SQLite databases unless `--skip-db`:
   - `data/marko/portfolio.db`
   - `data/_demo/portfolio.db`
   - `data/_system/users.db`
5. Creates `.env` from `.env.example` if not present
6. Runs `docker build` on the server
7. Stops old container, starts new one with volume mount and env file

## Post-deploy verification

```bash
# On server: check container is running
sudo docker ps --filter name=portfolio

# Check logs
sudo docker logs portfolio --tail 50

# Sync logs (cron job)
cat /home/homeassistant/portfolio-sync.log
```

## Force rebuild (no cache)

```bash
# SSH to server, then:
cd /home/homeassistant/revolut-edavki-converter
sudo docker build --no-cache -t revolut-edavki-converter-portfolio .
sudo docker rm -f portfolio
sudo docker run -d --name portfolio --restart unless-stopped -p 8081:8080 -v /home/homeassistant/revolut-edavki-converter/data:/data --env-file /home/homeassistant/revolut-edavki-converter/.env revolut-edavki-converter-portfolio
```

## When to use

Use this skill when asked to deploy, push to production, or update the server. Default to `--skip-db` for code-only changes unless database updates are explicitly needed.
