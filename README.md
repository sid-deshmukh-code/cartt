# Smart Shopping Cart — Raspberry Pi 4 (2GB) Touchscreen App

A touchscreen point-of-sale style cart: scan a barcode, item gets added with
live running total, adjust quantity or remove items, checkout through a
dummy payment gateway, get a receipt.

## 1. Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager** on your main computer.
2. Flash **Raspberry Pi OS (64-bit)** — the "Legacy/Bookworm with desktop"
   image is fine; the Lite (no desktop) image also works if you want a
   leaner kiosk boot, but it needs a bit more manual X11/Wayland setup.
3. In the Imager's advanced options (gear icon), pre-configure Wi-Fi,
   hostname, and enable SSH — saves you needing a keyboard/mouse later.
4. Boot the Pi with your touchscreen connected via HDMI + USB (for touch
   input) or the official DSI 7" display.

## 2. First boot setup

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-pip python3-venv git \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev \
    zlib1g-dev libgstreamer1.0-dev
```

These SDL2/gstreamer packages are Kivy's system dependencies for touch,
graphics, and (optional) camera/video support.

## 3. Get the project onto the Pi

Copy this `smart_cart/` folder to the Pi (via `scp`, a USB drive, or `git`),
e.g.:

```bash
scp -r smart_cart pi@<pi-ip-address>:/home/pi/
```

## 4. Install Python dependencies

```bash
cd ~/smart_cart
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> On a 2GB Pi 4, building Kivy from source is slow — the pinned version
> above has prebuilt wheels for common architectures, so `pip install`
> should just pull binaries. If it tries to compile from source, it'll
> still work, just budget 20-30 minutes.

## 5. Initialize the product database

```bash
python3 db.py
```

This creates `cart.db` (SQLite) with 10 sample products using simple dummy
barcodes for easy testing:

| Barcode | Product                | Price   |
|---------|-------------------------|---------|
| 001     | Parle-G Biscuits 200g   | Rs. 20  |
| 002     | Colgate Toothpaste 100g | Rs. 55  |
| 003     | Tata Salt 1kg           | Rs. 25  |
| 004     | Amul Butter 100g        | Rs. 52  |
| 005     | Maggi Noodles 70g       | Rs. 14  |
| 006     | Surf Excel 500g         | Rs. 65  |
| 007     | Britannia Bread 400g    | Rs. 40  |
| 008     | Dettol Soap 75g         | Rs. 35  |
| 009     | Lay's Chips 90g         | Rs. 20  |
| 010     | Coca-Cola 750ml         | Rs. 40  |

Type any of these codes (e.g. `001`) into the app's barcode field and press
Enter to add that item — no physical scanner required for this stage.

Replace/extend `sample_products` in `db.py` with your real product+barcode
list once you're ready, or write a small script to bulk-import from a CSV.

### Printing real scannable barcodes for testing

If you want to test the actual scanner hardware (not just typing codes),
generate printable Code128 barcode images for these dummy codes:

```bash
pip install python-barcode[images]
python3 generate_barcodes.py
```

This creates `barcodes/001.png` through `barcodes/010.png` — print them,
scan them, and confirm the scanner correctly "types" the code + Enter into
the app.

## 6. Run the app

```bash
python3 main.py
```

For actual deployment on the touchscreen (not desktop testing), edit
`main.py` and uncomment/set:

```python
Window.fullscreen = 'auto'
```

instead of the fixed `Window.size = (800, 480)` dev line.

## 7. (Optional) Auto-launch on boot as a kiosk

Add an autostart entry so the cart app launches full-screen automatically
when the Pi powers on (no login/desktop needed):

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/smartcart.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=SmartCart
Exec=/home/pi/smart_cart/venv/bin/python3 /home/pi/smart_cart/main.py
X-GNOME-Autostart-enabled=true
EOF
```

## How barcode scanning works here

Most USB/Bluetooth barcode scanners are **HID keyboard-wedge devices** —
to the Pi they look exactly like someone typing very fast on a keyboard,
followed by an Enter keypress. That's why the app just needs a text field
that's always focused: point the scanner at a barcode, it "types" the
digits + Enter into `barcode_input`, and `on_text_validate` fires to look
the product up and add it to the cart. No special USB driver or scanner
SDK is needed. The same field also accepts manual typing, which is handy
for testing without a physical scanner.

## Dummy payment gateway

`PaymentScreen.process_payment()` in `main.py` is where the fake gateway
lives — it just waits ~1.8s (`Clock.schedule_once`) to simulate network
latency, then marks the transaction as `SUCCESS`, logs it to the
`transactions` table, and shows a receipt popup. When you're ready to go
live, that block is the seam to swap in a real gateway's test-mode SDK
(Razorpay, Stripe, PayU, etc.) — keep the same success/failure callback
shape so the rest of the UI doesn't need to change.

## Cloud sync & admin dashboard (AWS)

Every checkout also pushes the transaction to an AWS RDS (MySQL) database
in real time, and a separate Flask admin dashboard (hosted on EC2) reads
from that same database to show sales and inventory to whoever's managing
the cart remotely.

- `aws/` — the Pi-side sync module (`rds_sync.py`) plus the RDS schema
  (`schema.sql`). Handles offline retries automatically if the Pi loses
  WiFi mid-checkout.
- `admin_webapp/` — the Flask dashboard: login-protected pages for
  today's revenue, transaction history, and product inventory.
- **Full walkthrough**: see [`AWS_DEPLOYMENT.md`](./AWS_DEPLOYMENT.md) for
  step-by-step RDS setup, security groups, EC2 hosting, and Pi
  configuration.

## Project files

| File              | Purpose                                             |
|-------------------|------------------------------------------------------|
| `main.py`         | Kivy GUI — cart screen + payment screen              |
| `db.py`           | SQLite schema, sample products, transaction logging  |
| `cart.db`         | Created on first run of `db.py` (not in version control) |
| `requirements.txt`| Python dependencies                                  |
| `aws/rds_sync.py` | Pushes transactions/products to AWS RDS in real time  |
| `aws/schema.sql`  | RDS (MySQL) table definitions                         |
| `admin_webapp/`   | Flask dashboard, deployed on EC2                      |
| `AWS_DEPLOYMENT.md` | Full AWS setup guide                                |

## Extending this

- **Real barcodes**: swap the sample products for your own barcode/price
  list — `add_or_update_product()` in `db.py` handles inserts/updates.
- **Stock deduction**: on successful payment, loop over `self.items` and
  decrement `stock` in the `products` table.
- **Admin screen**: add a third `Screen` for adding/editing products
  without touching the database directly.
- **Weight/RFID anti-theft check**: if you later add a weight sensor or
  exit gate (as in the separate anti-shoplifting cart build), this GUI's
  cart state is exactly what you'd reconcile against the sensor reading.
