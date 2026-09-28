#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu 22.04/24.04 server (e.g. Oracle Cloud Always Free, Ampere A1).
# Run on the server:  bash ~/remotehunt/deploy/setup-server.sh
set -euo pipefail

echo "==> Installing Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "==> Opening ports 80/443 in the OS firewall (Oracle images block them by default)"
if command -v iptables >/dev/null; then
  for p in 80 443; do
    sudo iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || \
      sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$p" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save; fi
fi
if command -v ufw >/dev/null && sudo ufw status | grep -q active; then
  sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
fi

echo "==> Adding 2 GB swap (safety net while building the image)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

cd "$(dirname "$0")/.."
for v in DOMAIN APP_PASSWORD FERNET_KEY; do
  if ! grep -qE "^${v}=.+" .env 2>/dev/null; then
    echo "!! ${v} is not set in $(pwd)/.env - set it, then run this script again."; exit 1
  fi
done

echo "==> Building and starting (first build takes ~10 minutes)"
sudo docker compose -f docker-compose.prod.yml up -d --build
sudo docker compose -f docker-compose.prod.yml ps
echo "==> Done. Open https://$(grep ^DOMAIN= .env | cut -d= -f2)"
