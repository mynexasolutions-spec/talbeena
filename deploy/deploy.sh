#!/bin/bash
# Talbeena — Deploy latest code to production
# Usage: bash deploy/deploy.sh

set -e

SERVER="ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com"
PEM="twoindia_deploy_config/nexa-solutions.pem"
REMOTE_DIR="/home/ec2-user/talbeena"
SERVICE="talbeena"

echo "==> Copying files to server..."
scp -i "$PEM" -o StrictHostKeyChecking=no -r \
  app.py \
  wsgi.py \
  extensions.py \
  helpers.py \
  db.py \
  queries.py \
  seed.py \
  requirements.txt \
  routes/ \
  templates/ \
  static/ \
  "$SERVER:$REMOTE_DIR/"

echo "==> Installing dependencies on server..."
ssh -i "$PEM" -o StrictHostKeyChecking=no "$SERVER" \
  "cd $REMOTE_DIR && source venv/bin/activate && pip install -r requirements.txt -q"

echo "==> Restarting service..."
ssh -i "$PEM" -o StrictHostKeyChecking=no "$SERVER" \
  "sudo systemctl restart $SERVICE && sleep 3 && sudo systemctl is-active $SERVICE"

echo ""
echo "Deployment complete! Site at https://htwoindia.in"
