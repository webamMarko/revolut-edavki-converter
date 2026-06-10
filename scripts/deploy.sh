#!/usr/bin/env bash
# Deploy or update the portfolio app on the remote server.
# Usage: ./scripts/deploy.sh [--skip-db]
#
# Options:
#   --skip-db   Skip copying databases (useful for code-only updates)
#
# Requirements: sshpass installed locally (brew install sshpass)

set -euo pipefail

REMOTE_USER="homeassistant"
REMOTE_HOST="192.168.4.213"
REMOTE_DIR="/home/homeassistant/revolut-edavki-converter"

if [[ -z "${REMOTE_PASS:-}" ]]; then
  read -rs -p "Password for ${REMOTE_USER}@${REMOTE_HOST}: " REMOTE_PASS
  echo
fi
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="portfolio"
IMAGE_NAME="revolut-edavki-converter-portfolio"

SKIP_DB=false
for arg in "$@"; do
  [[ "$arg" == "--skip-db" ]] && SKIP_DB=true
done

SSH="sshpass -p ${REMOTE_PASS} ssh -o StrictHostKeyChecking=no -o NumberOfPasswordPrompts=1"
SCP="sshpass -p ${REMOTE_PASS} scp -o StrictHostKeyChecking=no -o NumberOfPasswordPrompts=1"
SUDO="echo ${REMOTE_PASS} | sudo -S"

echo "==> Building deployment archive..."
TMPFILE=$(mktemp /tmp/portfolio-deploy-XXXXXX.tar.gz)
tar czf "$TMPFILE" \
  --exclude='./.git' \
  --exclude='./data' \
  --exclude='./.env' \
  --exclude='./venv' \
  --exclude='./.claude' \
  --exclude='./__pycache__' \
  --exclude='./*.pyc' \
  --exclude='./portfolio_report.html' \
  --exclude='./output.xml' \
  -C "$LOCAL_DIR" .
echo "   Archive size: $(du -sh "$TMPFILE" | cut -f1)"

echo "==> Uploading archive..."
$SCP "$TMPFILE" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/portfolio-deploy.tar.gz"
rm "$TMPFILE"

echo "==> Extracting on server..."
$SSH "${REMOTE_USER}@${REMOTE_HOST}" "
  mkdir -p ${REMOTE_DIR}
  cd ${REMOTE_DIR}
  tar xzf /tmp/portfolio-deploy.tar.gz 2>/dev/null || true
  rm -f /tmp/portfolio-deploy.tar.gz
"

if [[ "$SKIP_DB" == false ]]; then
  echo "==> Copying databases..."
  $SSH "${REMOTE_USER}@${REMOTE_HOST}" "
    mkdir -p ${REMOTE_DIR}/data/marko \
              ${REMOTE_DIR}/data/_demo \
              ${REMOTE_DIR}/data/_system
  "
  for db_path in \
    "data/marko/portfolio.db" \
    "data/_demo/portfolio.db" \
    "data/_system/users.db" \
    "data/_system/prices.db"; do
    local_file="${LOCAL_DIR}/${db_path}"
    if [[ -f "$local_file" ]]; then
      echo "   Copying ${db_path}..."
      $SCP "$local_file" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/${db_path}"
    else
      echo "   Skipping ${db_path} (not found locally)"
    fi
  done
fi

echo "==> Ensuring .env exists on server..."
$SSH "${REMOTE_USER}@${REMOTE_HOST}" "
  if [[ ! -f ${REMOTE_DIR}/.env ]]; then
    cp ${REMOTE_DIR}/.env.example ${REMOTE_DIR}/.env
    sed -i 's|APP_BASE_URL=.*|APP_BASE_URL=http://${REMOTE_HOST}:8081|' ${REMOTE_DIR}/.env
    echo '   Created .env from .env.example'
  else
    echo '   .env already exists, skipping'
  fi
"

echo "==> Building Docker image on server..."
$SSH "${REMOTE_USER}@${REMOTE_HOST}" "
  cd ${REMOTE_DIR}
  ${SUDO} docker build -t ${IMAGE_NAME} . 2>&1
"

echo "==> Restarting container..."
$SSH "${REMOTE_USER}@${REMOTE_HOST}" "
  ${SUDO} docker rm -f ${CONTAINER_NAME} 2>/dev/null || true
  ${SUDO} docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    -p 8081:8081 \
    -v ${REMOTE_DIR}/data:/data \
    --env-file ${REMOTE_DIR}/.env \
    ${IMAGE_NAME}
"

echo "==> Verifying container is running..."
$SSH "${REMOTE_USER}@${REMOTE_HOST}" "${SUDO} docker ps --filter name=${CONTAINER_NAME} --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

echo ""
echo "Done. App is live at http://${REMOTE_HOST}:8081"
