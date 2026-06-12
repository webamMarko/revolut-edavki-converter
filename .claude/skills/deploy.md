# Deploy Skill

Deploy the revolut-edavki-converter portfolio app to production. Use when asked to deploy, push to production, update the server, or release changes.

## Environment

- **This agent runs on the production server** (`192.168.4.213`) — deploy locally, no SSH needed.
- **Source repo:** `/home/homeassistant/ai-development/revolut-edavki-converter` (development copy with `.git`)
- **Server directory:** `/home/homeassistant/revolut-edavki-converter` (deployed copy, no `.git`)
- **App URL:** `http://192.168.4.213:8081`
- **Container:** `portfolio` (Docker, `--restart unless-stopped`)
- **Port mapping:** `8081:8081` (host:container) — always expose on **8081**
- **Data volume:** `/home/homeassistant/revolut-edavki-converter/data:/data`

## Deploy Procedure

### Step 1: Sync code

```bash
cd /home/homeassistant/ai-development/revolut-edavki-converter
tar czf /tmp/portfolio-deploy.tar.gz \
  --exclude='./.git' --exclude='./data' --exclude='./.env' \
  --exclude='./venv' --exclude='./.claude' --exclude='./__pycache__' \
  --exclude='./*.pyc' --exclude='./portfolio_report.html' --exclude='./output.xml' .
cd /home/homeassistant/revolut-edavki-converter
tar xzf /tmp/portfolio-deploy.tar.gz
rm /tmp/portfolio-deploy.tar.gz
```

### Step 2: Build Docker image

```bash
docker build -t revolut-edavki-converter-portfolio /home/homeassistant/revolut-edavki-converter/
```

### Step 3: Restart container

```bash
docker rm -f portfolio 2>/dev/null
docker run -d \
  --name portfolio \
  --restart unless-stopped \
  -p 8081:8081 \
  -v /home/homeassistant/revolut-edavki-converter/data:/data \
  --env-file /home/homeassistant/revolut-edavki-converter/.env \
  revolut-edavki-converter-portfolio
```

### Step 4: Verify

```bash
docker ps --filter name=portfolio --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/
```

Expect: container `Up`, HTTP `200`. Port must be `8081`.

## Database deploy (optional)

Only copy databases when explicitly requested. Source databases live in `ai-development/revolut-edavki-converter/data/`:

- `data/marko/portfolio.db` — primary user DB
- `data/_demo/portfolio.db` — demo/guest DB
- `data/_system/users.db` — user registry
- `data/_system/prices.db` — price cache

```bash
cp /home/homeassistant/ai-development/revolut-edavki-converter/data/marko/portfolio.db \
   /home/homeassistant/revolut-edavki-converter/data/marko/portfolio.db
# repeat for other DBs as needed
```

## Troubleshooting

```bash
docker logs portfolio --tail 50
cat /home/homeassistant/portfolio-sync.log
```

## Force rebuild (no cache)

```bash
docker build --no-cache -t revolut-edavki-converter-portfolio /home/homeassistant/revolut-edavki-converter/
```

## Cron job (on server)

```
15 22 * * 1-5 docker exec portfolio python -m src.cli sync >> /home/homeassistant/portfolio-sync.log 2>&1
```
