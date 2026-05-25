# Deploying Talbeena to AWS EC2

Deploys alongside your other project on the same instance.
Uses a different port (8004) and domain (htwoindia.in).

---

## Prerequisites

1. `htwoindia.in` DNS points to your EC2 IP (`13.200.255.139`)
2. The PEM key is at `twoindia_deploy_config/nexa-solutions.pem`

---

## Step 1: Initial Server Setup (one-time)

SSH into the server:
```bash
ssh -i twoindia_deploy_config/nexa-solutions.pem ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com
```

Create the directory and virtual environment:
```bash
mkdir -p /home/ec2-user/talbeena
cd /home/ec2-user/talbeena
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
exit
```

## Step 2: Install systemd Service

```bash
ssh -i twoindia_deploy_config/nexa-solutions.pem ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com
sudo nano /etc/systemd/system/talbeena.service
```

Paste the contents of `deploy/talbeena.service`, save (Ctrl+O), exit (Ctrl+X).

## Step 3: Configure Nginx

```bash
sudo nano /etc/nginx/conf.d/htwoindia.conf
```

Paste the contents of `deploy/htwoindia.conf`, save, exit.

## Step 4: Copy .env to Server (one-time)

The `.env` file has secrets — it must be copied separately:

```bash
scp -i twoindia_deploy_config/nexa-solutions.pem .env ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com:/home/ec2-user/talbeena/.env
```

Edit the `.env` on the server for production:
```
PRODUCTION=True
SESSION_COOKIE_SECURE=True
```

## Step 5: Enable Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable talbeena
sudo systemctl restart nginx
```

## Step 6: SSL Certificate (Certbot)

```bash
sudo certbot --nginx -d htwoindia.in -d www.htwoindia.in
```

Follow the prompts. Certbot auto-renews.

## Step 7: Deploy Code Updates

From your local PC:
```bash
bash deploy/deploy.sh
```

This copies code, installs deps, and restarts the service.

---

## Useful Commands

```bash
# Check service status
sudo systemctl status talbeena

# View logs
sudo journalctl -u talbeena -f

# Restart manually
sudo systemctl restart talbeena

# Test Nginx config
sudo nginx -t
sudo systemctl reload nginx
```
