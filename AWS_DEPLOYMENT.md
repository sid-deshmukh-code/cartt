# AWS Deployment Guide — RDS + EC2 Admin Dashboard

This wires the Pi's cart up to a real cloud backend:

```
Raspberry Pi (cart)  --push each transaction-->  AWS RDS (MySQL)
                                                       ^
                                                       |  reads
                                              EC2 (Flask admin dashboard)
                                                       ^
                                                       |  https
                                              You, in a browser
```

Do the steps in this order — RDS first, then EC2, then the Pi.

## 1. Create the RDS MySQL instance

1. AWS Console → **RDS** → **Create database**.
2. Engine: **MySQL**. Template: **Free tier** (fine for a student project).
3. DB instance identifier: `smart-cart-db`. Set a strong master password —
   save it somewhere, you'll need it once to run `schema.sql`.
4. Under **Connectivity**: note the VPC it's created in (default VPC is
   fine). Set **Public access: Yes** for now so the Pi (which is on your
   home network, not inside AWS) can reach it directly. This is the
   simplest setup for a project — see the security note at the end for
   what to tighten for anything beyond a demo.
5. Create it. Wait a few minutes for status to become "Available", then
   copy its **endpoint** (looks like
   `smart-cart-db.xxxxxxxxxx.ap-south-1.rds.amazonaws.com`) — you'll need
   it repeatedly below.

## 2. Open the security group

RDS instances sit behind a security group that blocks all inbound traffic
by default.

1. RDS console → your instance → **Connectivity & security** → click the
   VPC security group.
2. **Inbound rules → Edit inbound rules → Add rule**:
   - Type: MySQL/Aurora (port 3306)
   - Source: **My IP** (this covers your laptop, for running `schema.sql`
     and testing). Add a second rule the same way for the Pi's public IP
     once you know it (`curl ifconfig.me` on the Pi).
   - You'll add a third rule for the EC2 instance's security group once
     you create it in step 4.

Home internet IPs change occasionally — if the Pi loses its sync
connection later, check whether its public IP changed and update this
rule.

## 3. Apply the schema

From your laptop (needs the `mysql` CLI — `sudo apt install mysql-client`
on Linux, or use MySQL Workbench / TablePlus if you prefer a GUI):

```bash
mysql -h <rds-endpoint> -P 3306 -u <master-user> -p < aws/schema.sql
```

Then create the two least-privilege users (open a MySQL shell with the
same command minus the `< aws/schema.sql` part, or run these as a
follow-up script) — see the commented-out `CREATE USER` statements at the
bottom of `aws/schema.sql`. Use these, not the master user, everywhere
else from here on:

- `pi_writer` — the Pi uses this. Can only insert transactions and
  read/write products.
- `dashboard_reader` — the admin webapp uses this. Read-only.

## 4. Launch the EC2 instance (for the admin dashboard)

1. EC2 console → **Launch instance**. Ubuntu 22.04/24.04, `t2.micro`
   (free tier).
2. Create/select a key pair (`.pem`) so you can SSH in.
3. Security group: allow **SSH (22)** from your IP, and **HTTP (80)**
   from anywhere (`0.0.0.0/0`) so the dashboard is reachable.
4. Launch it, note its **public IP**.
5. Go back to the RDS security group (step 2) and add a rule allowing
   port 3306 from this EC2 instance's security group — this is how the
   dashboard reaches the database.

SSH in and set up the app:

```bash
ssh -i your-key.pem ubuntu@<ec2-public-ip>

sudo apt update && sudo apt install -y python3-pip python3-venv nginx

# copy admin_webapp/ over, e.g. from your laptop:
#   scp -i your-key.pem -r admin_webapp ubuntu@<ec2-public-ip>:~/

cd ~/admin_webapp
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # fill in RDS_HOST, dashboard_reader credentials, FLASK_SECRET_KEY

python3 create_admin.py admin <choose-a-password>   # one-time login setup
```

Run it as a background service with `systemd` so it survives reboots:

```bash
sudo tee /etc/systemd/system/smartcart-admin.service << 'EOF'
[Unit]
Description=Smart Cart Admin Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/admin_webapp
Environment="PATH=/home/ubuntu/admin_webapp/venv/bin"
ExecStart=/home/ubuntu/admin_webapp/venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now smartcart-admin
```

Put nginx in front so it's reachable on plain port 80:

```bash
sudo tee /etc/nginx/sites-available/smartcart << 'EOF'
server {
    listen 80;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/smartcart /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl restart nginx
```

Visit `http://<ec2-public-ip>` — you should see the login page.

## 5. Configure the Pi

```bash
cd ~/smart_cart
source venv/bin/activate
pip install pymysql python-dotenv

cp aws/.env.example aws/.env
nano aws/.env   # fill in RDS_HOST, pi_writer credentials
```

Push the current local product catalog up once:

```bash
python3 aws/rds_sync.py
```

That's it — `main.py` already calls `rds_sync.push_transaction_async(...)`
right after every successful checkout, and retries anything that failed
to send (e.g. WiFi drop) every 60 seconds automatically.

## Security notes (read before treating this as production)

This guide optimizes for "get it working for a college project" over
"production-grade." Before this ever handles real payments or real
customer data:

- **Public RDS access** (step 1) means the database is reachable from the
  internet, restricted only by security group IP rules. Home IPs change;
  a stricter setup would put the Pi on a VPN into the VPC instead, or use
  RDS Proxy / IAM auth. For a demo, IP-restricted security groups are a
  reasonable middle ground — just don't leave the rule as `0.0.0.0/0`.
- **HTTPS**: the EC2 dashboard is plain HTTP in this guide. For anything
  beyond local testing, put it behind an Application Load Balancer with
  an ACM certificate, or use `certbot` for a free Let's Encrypt cert once
  you have a domain name pointed at the instance.
- **Credentials**: `.env` files hold real passwords — never commit them.
  Both `.env.example` files are safe to commit; the real `.env` files are
  not (add `*.env` to `.gitignore` if you haven't).
- **Least privilege**: this is why `pi_writer` and `dashboard_reader` exist
  instead of using the RDS master user everywhere — if the Pi or the EC2
  instance is ever compromised, the blast radius is limited to what that
  one user can do.
