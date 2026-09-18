"""
main.py - Smart Shopping Cart touchscreen GUI (Kivy)

Run on Raspberry Pi 4 (2GB) + official 7" touchscreen (or any HDMI touch panel).

Flow:
  Barcode scanner (HID/"keyboard wedge") types digits + Enter into a
  hidden always-focused TextInput -> product looked up in SQLite ->
  added to cart -> quantity +/- and delete supported ->
  Checkout -> dummy Payment screen -> simulated processing -> receipt.

Run:
    python3 main.py

First-time setup:
    python3 db.py     # creates cart.db with sample products
"""

import json
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty, ObjectProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label

import db

# ---------------------------------------------------------------------------
# For dev/testing on a desktop (no touchscreen), keep a normal window size.
# On the actual Pi touchscreen deployment, launch full-screen instead:
#   Window.fullscreen = 'auto'
# ---------------------------------------------------------------------------
Window.size = (800, 480)  # matches the official 7" Pi touchscreen resolution


KV = """
#:import utils kivy.utils

# ---------------------------------------------------------------------
# Type scale — every font_size below maps to one of these roles so the
# whole app reads as one consistent hierarchy instead of ad-hoc sizes:
#   12sp  caption      - column headers, tiny meta labels
#   13sp  overline     - ALL CAPS section labels (SCAN PRODUCT, etc.)
#   14sp  body-small   - secondary text: prices, status/help messages
#   16sp  body         - product names, table values, secondary buttons
#   18sp  button-cta   - primary call-to-action buttons (Add/Checkout/Pay)
#   20sp  input        - the barcode field (biggest interactive text)
#   22sp  title        - screen headers (Smart Shopping Cart / Checkout)
#   22sp  stat-secondary - Total Weight (secondary KPI on cart screen)
#   30sp  stat-primary   - Total Amount (the #1 number on the cart screen)
#   36sp  stat-hero      - Amount Due (the biggest number in the whole app)
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Reusable styled widgets
# ---------------------------------------------------------------------

<SectionLabel@Label>:
    color: 0.42, 0.45, 0.52, 1
    bold: True
    font_size: '13sp'
    size_hint_y: None
    height: dp(22)
    halign: 'left'
    valign: 'middle'
    text_size: self.size

<RoundButton@Button>:
    bg_color: 0.20, 0.47, 0.90, 1
    bg_color_down: 0.14, 0.36, 0.74, 1
    background_color: 0, 0, 0, 0
    background_normal: ''
    background_down: ''
    color: 1, 1, 1, 1
    bold: True
    canvas.before:
        Color:
            rgba: self.bg_color_down if self.state == 'down' else self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [10]

<RoundToggle@ToggleButton>:
    bg_color: 1, 1, 1, 1
    bg_color_active: 0.16, 0.55, 0.38, 1
    border_color: 0.82, 0.84, 0.88, 1
    background_color: 0, 0, 0, 0
    background_normal: ''
    background_down: ''
    color: (1, 1, 1, 1) if self.state == 'down' else (0.15, 0.17, 0.2, 1)
    bold: True
    canvas.before:
        Color:
            rgba: self.bg_color_active if self.state == 'down' else self.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [10]
        Color:
            rgba: self.border_color
        Line:
            rounded_rectangle: [self.x, self.y, self.width, self.height, 10]
            width: 1.2

<RoundedInput@TextInput>:
    background_normal: ''
    background_active: ''
    background_color: 0, 0, 0, 0
    foreground_color: 0.12, 0.12, 0.14, 1
    hint_text_color: 0.6, 0.6, 0.63, 1
    cursor_color: 0.18, 0.45, 0.86, 1
    padding: [dp(16), dp(14), dp(10), dp(10)]
    canvas.before:
        Color:
            rgba: 0.97, 0.975, 0.99, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [10]
        Color:
            rgba: (0.20, 0.47, 0.90, 1) if self.focus else (0.85, 0.86, 0.89, 1)
        Line:
            rounded_rectangle: [self.x, self.y, self.width, self.height, 10]
            width: 1.4 if self.focus else 1

<Card@BoxLayout>:
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.06
        RoundedRectangle:
            pos: self.x - 1, self.y - 3
            size: self.size
            radius: [12]
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [12]

# ---------------------------------------------------------------------
# Cart row
# ---------------------------------------------------------------------

<CartRow>:
    size_hint_y: None
    height: dp(58)
    padding: dp(10), dp(4)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: 0.90, 0.91, 0.93, 1
        Line:
            points: [self.x + 4, self.y, self.x + self.width - 4, self.y]
            width: 1

    Label:
        text: root.name
        color: 0.14, 0.14, 0.16, 1
        halign: 'left'
        valign: 'middle'
        text_size: self.size
        size_hint_x: 0.30
        font_size: '16sp'
        shorten: True

    Label:
        text: f"Rs. {root.price:.2f}"
        color: 0.4, 0.4, 0.43, 1
        size_hint_x: 0.13
        font_size: '14sp'

    BoxLayout:
        size_hint_x: 0.22
        spacing: dp(6)
        padding: dp(2)
        RoundButton:
            text: '-'
            font_size: '16sp'
            bg_color: 0.90, 0.91, 0.93, 1
            bg_color_down: 0.80, 0.82, 0.85, 1
            color: 0.15, 0.15, 0.17, 1
            on_release: root.change_qty(-1)
        Label:
            text: str(root.qty)
            color: 0.1, 0.1, 0.1, 1
            font_size: '16sp'
            bold: True
            size_hint_x: 0.6
        RoundButton:
            text: '+'
            font_size: '16sp'
            on_release: root.change_qty(1)

    Label:
        text: root.weight_display
        color: 0.30, 0.45, 0.68, 1
        size_hint_x: 0.15
        font_size: '14sp'
        bold: True

    Label:
        text: f"Rs. {root.subtotal:.2f}"
        color: 0.05, 0.05, 0.05, 1
        bold: True
        size_hint_x: 0.13
        font_size: '16sp'

    RoundButton:
        text: 'X'
        size_hint_x: 0.07
        bg_color: 0.88, 0.30, 0.32, 1
        bg_color_down: 0.72, 0.20, 0.22, 1
        font_size: '15sp'
        on_release: root.remove_self()

# ---------------------------------------------------------------------
# Cart screen
# ---------------------------------------------------------------------

<CartScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: 0
        spacing: 0
        canvas.before:
            Color:
                rgba: 0.94, 0.945, 0.96, 1
            Rectangle:
                pos: self.pos
                size: self.size

        # ---- Header bar ----
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(64)
            padding: dp(16), dp(8)
            canvas.before:
                Color:
                    rgba: 0.11, 0.14, 0.20, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            BoxLayout:
                Label:
                    text: 'Smart Shopping Cart'
                    font_size: '22sp'
                    bold: True
                    color: 1, 1, 1, 1
                    halign: 'left'
                    valign: 'bottom'
                    text_size: self.size
                Label:
                    text: root.status_text
                    font_size: '14sp'
                    color: 0.45, 0.85, 0.55, 1
                    size_hint_x: 0.42
                    halign: 'right'
                    valign: 'bottom'
                    text_size: self.size
            Label:
                text: 'Self-checkout kiosk'
                font_size: '13sp'
                color: 0.62, 0.66, 0.74, 1
                halign: 'left'
                valign: 'top'
                text_size: self.size
                size_hint_y: None
                height: dp(18)

        # ---- Body ----
        BoxLayout:
            orientation: 'vertical'
            padding: dp(16)
            spacing: dp(12)

            # Scan panel
            Card:
                orientation: 'vertical'
                size_hint_y: None
                height: dp(120)
                padding: dp(16), dp(12)
                spacing: dp(10)

                SectionLabel:
                    text: 'SCAN PRODUCT'
                    height: dp(22)

                BoxLayout:
                    spacing: dp(12)
                    RoundedInput:
                        id: barcode_input
                        hint_text: 'Scan barcode or type it here, then press Enter'
                        multiline: False
                        font_size: '20sp'
                        on_text_validate: root.on_barcode_scanned(self.text)
                        focus: True
                    RoundButton:
                        text: 'Add'
                        size_hint_x: 0.2
                        font_size: '18sp'
                        on_release: root.on_barcode_scanned(barcode_input.text)

            # Items panel
            Card:
                orientation: 'vertical'
                padding: dp(14), dp(8)
                spacing: dp(4)

                SectionLabel:
                    text: 'ITEMS IN CART'

                # Column headers
                BoxLayout:
                    size_hint_y: None
                    height: dp(24)
                    padding: dp(10), 0
                    spacing: dp(6)
                    canvas.before:
                        Color:
                            rgba: 0.92, 0.93, 0.95, 1
                        Rectangle:
                            pos: self.x, self.y
                            size: self.width, 1
                    Label:
                        text: 'Product'
                        size_hint_x: 0.30
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                        halign: 'left'
                        text_size: self.size
                    Label:
                        text: 'Price'
                        size_hint_x: 0.13
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                    Label:
                        text: 'Qty'
                        size_hint_x: 0.22
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                    Label:
                        text: 'Weight'
                        size_hint_x: 0.15
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                    Label:
                        text: 'Subtotal'
                        size_hint_x: 0.13
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                    Label:
                        text: ''
                        size_hint_x: 0.07

                ScrollView:
                    GridLayout:
                        id: cart_list
                        cols: 1
                        size_hint_y: None
                        height: self.minimum_height
                        row_default_height: dp(58)

                Label:
                    text: 'Cart is empty - scan a product to begin'
                    opacity: 0 if root.has_items else 1
                    color: 0.65, 0.65, 0.68, 1
                    font_size: '14sp'
                    size_hint_y: None
                    height: 0 if root.has_items else dp(28)

            # ---- Summary panel ----
            Card:
                size_hint_y: None
                height: dp(96)
                padding: dp(16), dp(8)
                spacing: dp(18)

                BoxLayout:
                    orientation: 'vertical'
                    size_hint_x: 0.32
                    Label:
                        text: 'TOTAL AMOUNT'
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                        halign: 'left'
                        valign: 'bottom'
                        text_size: self.size
                        size_hint_y: None
                        height: dp(18)
                    Label:
                        text: f"Rs. {root.total:.2f}"
                        font_size: '30sp'
                        bold: True
                        color: 0.08, 0.08, 0.09, 1
                        halign: 'left'
                        valign: 'top'
                        text_size: self.size
                        shorten: True
                        size_hint_y: None
                        height: dp(44)

                BoxLayout:
                    orientation: 'vertical'
                    size_hint_x: 0.22
                    Label:
                        text: 'TOTAL WEIGHT'
                        font_size: '12sp'
                        bold: True
                        color: 0.55, 0.55, 0.58, 1
                        halign: 'left'
                        valign: 'bottom'
                        text_size: self.size
                        size_hint_y: None
                        height: dp(18)
                    Label:
                        text: root.total_weight_display
                        font_size: '22sp'
                        bold: True
                        color: 0.20, 0.42, 0.68, 1
                        halign: 'left'
                        valign: 'top'
                        text_size: self.size
                        shorten: True
                        size_hint_y: None
                        height: dp(32)

                Widget:
                    # spacer pushes buttons to the right
                    size_hint_x: 0.03

                RoundButton:
                    text: 'Clear Cart'
                    font_size: '16sp'
                    size_hint_x: 0.19
                    bg_color: 0.58, 0.60, 0.64, 1
                    bg_color_down: 0.46, 0.48, 0.52, 1
                    on_release: root.clear_cart()

                RoundButton:
                    text: 'Checkout'
                    font_size: '18sp'
                    size_hint_x: 0.24
                    bg_color: 0.16, 0.55, 0.38, 1
                    bg_color_down: 0.11, 0.42, 0.29, 1
                    on_release: root.go_to_checkout()

# ---------------------------------------------------------------------
# Payment screen
# ---------------------------------------------------------------------

<PaymentScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(16)
        spacing: 0
        canvas.before:
            Color:
                rgba: 0.94, 0.945, 0.96, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(48)
            Label:
                text: 'Checkout'
                font_size: '22sp'
                bold: True
                color: 0.1, 0.1, 0.1, 1
                halign: 'left'
                valign: 'middle'
                text_size: self.size

        Widget:
            size_hint_y: None
            height: dp(12)

        Card:
            orientation: 'vertical'
            padding: dp(22)
            spacing: dp(14)

            BoxLayout:
                orientation: 'vertical'
                size_hint_y: None
                height: dp(74)
                Label:
                    text: 'AMOUNT DUE'
                    font_size: '12sp'
                    bold: True
                    color: 0.55, 0.55, 0.58, 1
                Label:
                    text: f"Rs. {root.total:.2f}"
                    font_size: '34sp'
                    bold: True
                    color: 0.12, 0.45, 0.28, 1

            SectionLabel:
                text: 'SELECT PAYMENT METHOD'

            BoxLayout:
                size_hint_y: None
                height: dp(56)
                spacing: dp(10)
                RoundToggle:
                    id: btn_cash
                    text: 'Cash'
                    group: 'pay'
                    font_size: '17sp'
                    on_release: root.select_method('Cash')
                RoundToggle:
                    id: btn_card
                    text: 'Card'
                    group: 'pay'
                    font_size: '17sp'
                    on_release: root.select_method('Card')
                RoundToggle:
                    id: btn_upi
                    text: 'UPI'
                    group: 'pay'
                    font_size: '17sp'
                    on_release: root.select_method('UPI')

            Label:
                id: status_label
                text: root.status_text
                font_size: '15sp'
                color: 0.35, 0.35, 0.38, 1
                size_hint_y: None
                height: dp(26)

            Widget:
                # spacer

            BoxLayout:
                size_hint_y: None
                height: dp(56)
                spacing: dp(12)
                RoundButton:
                    text: 'Back to Cart'
                    font_size: '16sp'
                    bg_color: 0.58, 0.60, 0.64, 1
                    bg_color_down: 0.46, 0.48, 0.52, 1
                    on_release: root.go_back()
                RoundButton:
                    text: 'Pay Now'
                    font_size: '18sp'
                    bg_color: 0.16, 0.55, 0.38, 1
                    bg_color_down: 0.11, 0.42, 0.29, 1
                    on_release: root.process_payment()
"""


def format_weight(grams):
    """1000+ g shown as kg for readability, e.g. 1.25 kg vs 250 g."""
    if grams >= 1000:
        return f"{grams / 1000:.2f} kg"
    return f"{grams:.0f} g"


class CartRow(BoxLayout):
    barcode = StringProperty("")
    name = StringProperty("")
    price = NumericProperty(0.0)
    qty = NumericProperty(1)
    unit_weight = NumericProperty(0.0)  # grams, per single unit
    subtotal = NumericProperty(0.0)
    weight_display = StringProperty("")
    screen_ref = ObjectProperty(None)  # back-reference to CartScreen

    def on_kv_post(self, base_widget):
        self._refresh_weight_display()

    @property
    def total_weight(self):
        return self.unit_weight * self.qty

    def _refresh_weight_display(self):
        self.weight_display = format_weight(self.total_weight)

    def change_qty(self, delta):
        new_qty = self.qty + delta
        if new_qty < 1:
            return
        self.qty = new_qty
        self.subtotal = self.qty * self.price
        self._refresh_weight_display()
        if self.screen_ref:
            self.screen_ref.recalculate_total()

    def remove_self(self):
        if self.screen_ref:
            self.screen_ref.remove_item(self.barcode)


class CartScreen(Screen):
    total = NumericProperty(0.0)
    total_weight_display = StringProperty("0 g")
    status_text = StringProperty("Ready to scan")
    has_items = BooleanProperty(False)  # cart_rows is a plain dict, so this
                                         # drives the "empty cart" message in KV

    def on_kv_post(self, base_widget):
        # keep cart state as a dict keyed by barcode: {barcode: CartRow}
        self.cart_rows = {}
        self._focus_event = None

    def on_enter(self):
        # A physical barcode scanner "types" into whichever widget currently
        # has keyboard focus. Any tap elsewhere on screen (a +/- button, the
        # empty-cart area, etc.) can silently steal that focus away from the
        # scan field, at which point scans stop registering with no visible
        # error. This keeps re-claiming focus every 0.5s for as long as this
        # screen is showing, so scanning always just works.
        self.ids.barcode_input.focus = True
        self._focus_event = Clock.schedule_interval(self._ensure_scan_focus, 0.5)

    def on_leave(self):
        if self._focus_event:
            self._focus_event.cancel()
            self._focus_event = None

    def _ensure_scan_focus(self, dt):
        barcode_input = self.ids.get("barcode_input")
        if barcode_input and not barcode_input.focus:
            barcode_input.focus = True

    def on_barcode_scanned(self, barcode):
        barcode = barcode.strip()
        self.ids.barcode_input.text = ""
        if not barcode:
            return

        product = db.get_product_by_barcode(barcode)
        if not product:
            self.status_text = f"Unknown barcode: {barcode}"
            return

        if barcode in self.cart_rows:
            row = self.cart_rows[barcode]
            row.change_qty(1)
        else:
            row = CartRow(
                barcode=barcode,
                name=product["name"],
                price=product["price"],
                qty=1,
                unit_weight=product["weight_grams"],
                subtotal=product["price"],
                screen_ref=self,
            )
            self.cart_rows[barcode] = row
            self.ids.cart_list.add_widget(row)

        self.status_text = f"Added: {product['name']}"
        self.recalculate_total()

    def remove_item(self, barcode):
        row = self.cart_rows.pop(barcode, None)
        if row:
            self.ids.cart_list.remove_widget(row)
        self.recalculate_total()

    def recalculate_total(self):
        self.total = sum(r.subtotal for r in self.cart_rows.values())
        total_grams = sum(r.total_weight for r in self.cart_rows.values())
        self.total_weight_display = format_weight(total_grams)
        self.has_items = bool(self.cart_rows)

    def clear_cart(self):
        for row in list(self.cart_rows.values()):
            self.ids.cart_list.remove_widget(row)
        self.cart_rows = {}
        self.total = 0.0
        self.total_weight_display = "0 g"
        self.has_items = False
        self.status_text = "Cart cleared"

    def go_to_checkout(self):
        if not self.cart_rows:
            self.status_text = "Cart is empty"
            return
        payment_screen = self.manager.get_screen("payment")
        payment_screen.total = self.total
        payment_screen.items = [
            {
                "barcode": r.barcode,
                "name": r.name,
                "price": r.price,
                "qty": r.qty,
                "weight_grams": r.total_weight,
            }
            for r in self.cart_rows.values()
        ]
        payment_screen.status_text = ""
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "payment"

    def on_payment_success(self):
        self.clear_cart()
        self.status_text = "Payment successful. Ready for next customer."


class PaymentScreen(Screen):
    total = NumericProperty(0.0)
    status_text = StringProperty("")
    selected_method = StringProperty("")

    def on_kv_post(self, base_widget):
        self.items = []

    def select_method(self, method):
        self.selected_method = method
        self.status_text = f"{method} selected"

    def go_back(self):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "cart"

    def process_payment(self):
        if not self.selected_method:
            self.status_text = "Please select a payment method first"
            return

        self.status_text = f"Processing {self.selected_method} payment..."

        # --- DUMMY PAYMENT GATEWAY ---
        # Simulates network/processing delay. Replace this block with a real
        # gateway SDK call (Razorpay/Stripe/PayU test mode etc.) when ready.
        Clock.schedule_once(self._finish_payment, 1.8)

    def _finish_payment(self, dt):
        db.log_transaction(self.items, self.total, self.selected_method, status="SUCCESS")

        # Best-effort push to AWS RDS - runs on a background thread and
        # silently queues for retry if the Pi has no internet right now.
        # Never blocks or fails the checkout itself.
        try:
            from aws import rds_sync
            rds_sync.push_transaction_async(self.items, self.total, self.selected_method, status="SUCCESS")
        except Exception:
            pass

        self._show_receipt()

    def _show_receipt(self):
        lines = [f"{i['name']} x{i['qty']}  -  Rs. {i['price']*i['qty']:.2f}" for i in self.items]
        receipt_text = "\n".join(lines)
        receipt_text += f"\n\nTotal: Rs. {self.total:.2f}"
        receipt_text += f"\nPaid via: {self.selected_method}"
        receipt_text += f"\n{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"

        content = BoxLayout(orientation="vertical", padding=20, spacing=10)
        content.add_widget(Label(text="Payment Successful", font_size="22sp", bold=True,
                                  color=(0.1, 0.5, 0.1, 1), size_hint_y=None, height=40))
        content.add_widget(Label(text=receipt_text, halign="left", valign="top"))
        close_btn = None
        from kivy.uix.button import Button
        close_btn = Button(text="Done", size_hint_y=None, height=50)
        content.add_widget(close_btn)

        popup = Popup(title="Receipt", content=content, size_hint=(0.8, 0.7), auto_dismiss=False)
        close_btn.bind(on_release=lambda *a: self._close_receipt(popup))
        popup.open()

    def _close_receipt(self, popup):
        popup.dismiss()
        cart_screen = self.manager.get_screen("cart")
        cart_screen.on_payment_success()
        self.selected_method = ""
        for child in list(self.children):
            pass
        # reset toggle buttons visual state
        self.ids.btn_cash.state = "normal"
        self.ids.btn_card.state = "normal"
        self.ids.btn_upi.state = "normal"
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "cart"


class SmartCartApp(App):
    def build(self):
        db.init_db()
        Builder.load_string(KV)
        sm = ScreenManager()
        sm.add_widget(CartScreen(name="cart"))
        sm.add_widget(PaymentScreen(name="payment"))

        # Retry any AWS RDS syncs that failed earlier (e.g. WiFi drop
        # mid-checkout) every 60s, without ever blocking the UI thread.
        try:
            from aws import rds_sync
            Clock.schedule_interval(lambda dt: rds_sync.retry_pending_async(), 60)
        except Exception:
            pass

        return sm


if __name__ == "__main__":
    SmartCartApp().run()
