# Deploy RemoteHunt for free (Oracle Cloud Always Free)

Cost: **₹0 / $0**. Oracle's Always Free tier includes an ARM server with up to 4 CPUs and 24 GB RAM, forever. Add a free DuckDNS domain and a free Let's Encrypt certificate (issued automatically by Caddy) and nothing costs money.

What you get: `https://<yourname>.duckdns.org`, password-protected, running 24/7. The 6-hourly search, the 08:00 IST digest and the weekly and monthly reports all run without your Mac being on.

> Oracle asks for a card during sign-up **for identity verification only**. Always Free resources are never charged. Don't click "Upgrade to Pay As You Go" and you can't be billed.

---

## 1. Create the free server (~15 min)

1. Sign up at <https://signup.cloud.oracle.com/>. Pick **India South (Hyderabad)** or **India West (Mumbai)** as your home region. You can't change the region later.
2. Go to **Menu → Compute → Instances → Create instance**:
   - **Image:** Canonical **Ubuntu 24.04** (or 22.04).
   - **Shape:** *Change shape → Ampere →* **VM.Standard.A1.Flex**, **2 OCPU / 12 GB RAM**. This is still free: up to 4 OCPU and 24 GB total.
   - **SSH keys:** *Save private key* (download it, e.g. `oracle.key`).
   - Click **Create**. If you see **"Out of capacity"**, try another availability domain, or retry later. This is common for the free ARM shape.
3. Copy the instance's **Public IP address**.
4. Open ports 80 and 443 in Oracle's network firewall:
   - Go to **Instance → Subnet → Default Security List → Add Ingress Rules**.
   - Source CIDR `0.0.0.0/0`, TCP, destination port `80`. Add it.
   - Repeat for port `443`.

## 2. Get a free domain (~2 min)

1. Go to <https://www.duckdns.org>, sign in with GitHub or Google, and create a subdomain such as `parthhunt`. That gives you **`parthhunt.duckdns.org`**.
2. In the **current ip** box, paste the server's public IP and click **update ip**.

## 3. Copy the project to the server

On your Mac:

```bash
chmod 600 ~/Downloads/oracle.key
cd ~/remotehunt
rsync -az --exclude .venv --exclude frontend/node_modules --exclude frontend/dist --exclude .git \
  -e "ssh -i ~/Downloads/oracle.key" ./ ubuntu@<PUBLIC_IP>:~/remotehunt/
```

This also copies `data/` (your resume versions, jobs, tracker, API budgets) and `.env`, so the deployed app starts with everything you already have. Leave out `data/` if you'd rather start fresh.

## 4. Configure and start

```bash
ssh -i ~/Downloads/oracle.key ubuntu@<PUBLIC_IP>
cd ~/remotehunt
nano .env
```

Set these in `.env`:

```
DOMAIN=parthhunt.duckdns.org
APP_PASSWORD=<a long password you'll use to log in>
```

Keep the existing `FERNET_KEY`, `GROQ_API_KEY` and `GOOGLE_*` values. Then run:

```bash
bash deploy/setup-server.sh
```

The script installs Docker, opens ports 80/443 in the OS firewall, adds swap, then builds and starts the app. The first build takes about 10 minutes. Then open **https://parthhunt.duckdns.org** and log in with `APP_PASSWORD`.

## 5. Point Gmail at the new address

In Google Cloud (**Google Auth Platform**):

1. **Clients → RemoteHunt → Authorized redirect URIs → Add URI:** `https://parthhunt.duckdns.org/api/gmail/auth/callback`. Keep the localhost one too, so local use still works. Save.
2. **Branding → Authorized domains:** add `parthhunt.duckdns.org` if Google asks for it.
3. In the deployed app, go to **Settings → Connect Gmail** and sign in again. Tokens are encrypted with the same `FERNET_KEY`, so they carry over.

## Everyday commands (on the server)

| Task | Command |
|---|---|
| Logs | `sudo docker compose -f docker-compose.prod.yml logs -f backend` |
| Restart | `sudo docker compose -f docker-compose.prod.yml restart` |
| Update after changes on your Mac | re-run the `rsync` from step 3 **without** `data/` (add `--exclude data`), then `sudo docker compose -f docker-compose.prod.yml up -d --build` |
| Back up your data | `rsync -az -e "ssh -i ~/Downloads/oracle.key" ubuntu@<IP>:~/remotehunt/data/ ~/remotehunt-backup/` |
| Stop | `sudo docker compose -f docker-compose.prod.yml down` |

## Security notes

- **Login:** every API route except health, login and the Google callback requires a signed, HttpOnly, Secure session cookie. Login attempts are limited to 5 per 5 minutes per IP.
- **Password required:** the backend refuses to start over HTTPS without `APP_PASSWORD`.
- **Exposed ports:** only 80 and 443. The backend and frontend containers aren't published on the server.
- **Secrets:** they live only in `.env` on the server, which is readable only by your user.
- **Access:** anyone who has your password can see your resume and act on your Gmail (drafts, labels, digest-to-self). Use a strong, unique password.

## Free alternative: keep it on your Mac

To avoid creating a cloud account, run it on your Mac and expose it with a **Cloudflare Tunnel** (free), set `APP_PASSWORD`, and use the tunnel URL as `DOMAIN`. It only runs while your Mac is on and awake, so searches and the 08:00 digest are skipped when the Mac sleeps.
