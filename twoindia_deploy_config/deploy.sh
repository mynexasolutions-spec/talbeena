#!/bin/bash
# Two India — Deploy latest Flask code to production
# Usage: bash deploy.sh

set -e

SERVER="ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com"
PEM="nexa-solutions.pem"
REMOTE_DIR="/home/ec2-user/twoindia"
SERVICE="two-india"

echo "==> Copying updated files to server..."
# NOTE: Customize the files/folders you want to copy (e.g. app, templates, static, requirements.txt)
scp -i "$PEM" -o StrictHostKeyChecking=no -r \
  app \
  requirements.txt \
  "$SERVER:$REMOTE_DIR/"

echo "==> Restarting service..."
ssh -i "$PEM" -o StrictHostKeyChecking=no "$SERVER" \
  "sudo systemctl restart $SERVICE && sleep 3 && sudo systemctl is-active $SERVICE"

echo ""
echo "✅ Deployment complete! Site is live at https://twoindia.in"
