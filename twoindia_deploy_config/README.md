# Deploying Two India (Flask Backend) to AWS EC2

This guide walks you through deploying your Flask application (`twoindia`) on the **same EC2 instance** alongside your existing application.

---

## Files in this Setup

1. `nexa-solutions.pem`: The SSH private key used to connect to your AWS EC2 instance.
2. `deploy.sh`: The local script you will execute on your PC to push new code to AWS.
3. `two-india.service`: The systemd service configuration file for running Flask in the background on port `8003`.
4. `twoindia.conf`: The Nginx configuration file for pointing `twoindia.in` to port `8003`.

---

## Step 1: Copy this Config Folder
Move the files in this config directory to your Flask project directory on your PC. The directory structure should look like this:
```
twoindia/
├── app/ (your Flask application package)
├── wsgi.py (or main entry point)
├── requirements.txt
├── deploy.sh
├── nexa-solutions.pem
├── two-india.service
└── twoindia.conf
```

---

## Step 2: Configure Server Directories and Virtualenv
Connect to your server via SSH:
```bash
ssh -i nexa-solutions.pem ec2-user@ec2-13-200-255-139.ap-south-1.compute.amazonaws.com
```

Once logged into EC2, run these commands to set up the directories and a clean virtual environment:
```bash
# Create the deployment directory
mkdir -p /home/ec2-user/twoindia
cd /home/ec2-user/twoindia

# Create the virtual environment
python3 -m venv venv

# Activate venv and update pip
source venv/bin/activate
pip install --upgrade pip
```

---

## Step 3: Install the systemd Service
Copy the systemd service file onto the server's system directory to keep your app running in the background.

On the server, run:
```bash
# Open a new file to paste the service config
sudo nano /etc/systemd/system/two-india.service
```
Copy and paste the contents of `two-india.service` into it, save (`Ctrl+O`), and exit (`Ctrl+X`).

*Note: If you have environment variables, create a `.env` file at `/home/ec2-user/twoindia/.env` on the server containing your variables.*

---

## Step 4: Configure Nginx
Create the Nginx block to handle traffic for `twoindia.in`.

On the server, run:
```bash
sudo nano /etc/nginx/conf.d/twoindia.conf
```
Copy and paste the contents of `twoindia.conf` into it, save, and exit.

---

## Step 5: Enable Services and Restart Nginx
Tell systemd and Nginx to load the new configurations:
```bash
# Reload systemd and enable your new Flask app service
sudo systemctl daemon-reload
sudo systemctl enable two-india

# Restart Nginx
sudo systemctl restart nginx
```

---

## Step 6: Deploy Code
On your local PC, open a terminal (like Git Bash) in your `twoindia` directory and run:
```bash
bash deploy.sh
```
This will:
1. Copy your code using `scp`.
2. Automatically restart the `two-india` service on the server.

---

## Step 7: Update DNS & SSL (HTTPS)
1. In your domain registrar (GoDaddy, Namecheap, etc.), point the DNS `A` record for `twoindia.in` and `www` to your EC2 public IP: **`13.200.255.139`**.
2. Run Certbot on the EC2 instance to automatically obtain and configure SSL for your new domain:
   ```bash
   sudo certbot --nginx -d twoindia.in -d www.twoindia.in
   ```
