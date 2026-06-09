# -*- coding: utf-8 -*-
# rhino_api_sender_2.py
# Popup panel to build and send an A-Line to the bowl backend.

import json
import threading
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
import Eto.Forms as forms
import Eto.Drawing as drawing
import System
import System.Net
import System.Text

BASE_URL = "https://bowl-backend-x0jz.onrender.com"

# ── Theme ────────────────────────────────────────────────────────────────────
COL_BG       = drawing.Color.FromArgb(26,  26,  26)   # #1A1A1A dark background
COL_SURFACE  = drawing.Color.FromArgb(40,  40,  40)   # #282828 input fields
COL_ACCENT   = drawing.Color.FromArgb(190,  0, 255)   # #BE00FF magenta
COL_TEXT     = drawing.Color.FromArgb(255, 255, 255)   # white
COL_MUTED    = drawing.Color.FromArgb(160, 160, 160)   # grey labels


# ── Geometry helpers ─────────────────────────────────────────────────────────

def coerce_curve(obj):
    geo = obj.CurveGeometry if hasattr(obj, "CurveGeometry") else getattr(obj, "Geometry", None)
    if geo is None:
        return None
    if isinstance(geo, rg.PolylineCurve):
        return geo
    if isinstance(geo, rg.Curve):
        return geo
    return None


def extract_2d_points(curve, is_closed):
    ok, poly = curve.TryGetPolyline()
    if not ok:
        return None, "input is not a polyline — use a Polyline or convert with _Convert"

    pts = [(p.X, p.Y) for p in poly]

    if is_closed and len(pts) >= 2:
        if abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
            pts = pts[:-1]

    if len(pts) < 3:
        return None, "need at least 3 distinct points (got {0})".format(len(pts))

    return pts, None


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def post_json(url, data, token=None):
    try:
        client = System.Net.WebClient()
        client.Headers.Add("Content-Type", "application/json")
        client.Headers.Add("Accept", "application/json")
        if token:
            client.Headers.Add("Authorization", "Bearer " + token)
        body = json.dumps(data)
        response = client.UploadString(url, "POST", body)
        return json.loads(response)
    except System.Net.WebException as e:
        resp = e.Response
        detail = ""
        if resp:
            stream = resp.GetResponseStream()
            reader = System.IO.StreamReader(stream)
            detail = reader.ReadToEnd()
        raise RuntimeError("HTTP error: {0} — {1}".format(str(e.Message), detail[:300]))
    except Exception as e:
        raise RuntimeError(str(e))


def login(email, password):
    resp = post_json(BASE_URL + "/api/v1/auth/login", {"email": email, "password": password})
    token = resp.get("token")
    if not token:
        raise RuntimeError("login succeeded but no token returned")
    return token


def create_aline(token, name, is_closed, pts):
    body = {
        "name": name,
        "closed": is_closed,
        "points": [{"x": x, "y": y} for x, y in pts],
    }
    return post_json(BASE_URL + "/api/v1/alines", body, token=token)


# ── UI helpers ───────────────────────────────────────────────────────────────

def make_label(text, muted=False):
    l = forms.Label()
    l.Text = text
    l.TextColor = COL_MUTED if muted else COL_TEXT
    return l


def style_textbox(tb):
    tb.BackgroundColor = COL_SURFACE
    tb.TextColor = COL_TEXT
    return tb


def style_button(btn, accent=False):
    btn.BackgroundColor = COL_ACCENT if accent else COL_SURFACE
    btn.TextColor = COL_TEXT
    return btn


# ── Dialog ───────────────────────────────────────────────────────────────────

class ALineSenderDialog(forms.Form):

    def __init__(self):
        self.selected_curve_ids = []

        self.Title = "Seating Bowl Generator - Rhino Connector"
        self.Resizable = False
        self.AutoSize = True
        self.BackgroundColor = COL_BG

        # ── Fields ──────────────────────────────────────────────────────────
        self.txt_email = style_textbox(forms.TextBox())
        self.txt_email.PlaceholderText = "user@example.com"
        self.txt_email.Width = 340

        self.txt_password = style_textbox(forms.PasswordBox())
        self.txt_password.Width = 340
        self.txt_password.Height = self.txt_email.Height if self.txt_email.Height > 0 else 22

        self.txt_name = style_textbox(forms.TextBox())
        self.txt_name.PlaceholderText = "A-Line name"
        self.txt_name.Width = 340

        self.chk_closed = forms.CheckBox()
        self.chk_closed.Text = "Closed Polyline  ✓"
        self.chk_closed.Checked = True
        self.chk_closed.TextColor = COL_TEXT

        self.btn_select = style_button(forms.Button())
        self.btn_select.Text = "Select Curve in Rhino"
        self.btn_select.Width = 220
        self.btn_select.Click += self.on_select_curve

        self.lbl_curve_status = make_label("No curve selected.", muted=True)

        self.lbl_status = forms.Label()
        self.lbl_status.Text = ""
        self.lbl_status.Width = 340
        self.lbl_status.TextColor = COL_ACCENT

        self.btn_send = style_button(forms.Button(), accent=True)
        self.btn_send.Text = "Send A-Line"
        self.btn_send.MinimumSize = drawing.Size(160, 30)
        self.btn_send.Size = drawing.Size(160, 30)
        self.btn_send.Click += self.on_send

        self.btn_close = style_button(forms.Button())
        self.btn_close.Text = "Close"
        self.btn_close.MinimumSize = drawing.Size(100, 30)
        self.btn_close.Size = drawing.Size(100, 30)
        self.btn_close.Click += self.on_close

        # ── Layout ──────────────────────────────────────────────────────────
        layout = forms.DynamicLayout()
        layout.Padding = drawing.Padding(20)
        layout.Spacing = drawing.Size(0, 10)
        layout.DefaultSpacing = drawing.Size(6, 6)
        layout.BackgroundColor = COL_BG

        layout.AddRow(make_label("Email"))
        layout.AddRow(self.txt_email)
        layout.AddRow(make_label("Password"))
        layout.AddRow(self.txt_password)
        layout.AddRow(make_label("A-Line Name"))
        layout.AddRow(self.txt_name)
        layout.AddRow(self.chk_closed)
        layout.AddRow(self.btn_select)
        layout.AddRow(self.lbl_curve_status)
        layout.AddRow(self.lbl_status)

        btn_row = forms.TableLayout()
        btn_row.Spacing = drawing.Size(10, 0)
        btn_row.BackgroundColor = COL_BG
        btn_row.Rows.Add(forms.TableRow(
            forms.TableCell(self.btn_send, False),
            forms.TableCell(self.btn_close, False),
        ))

        btn_panel = forms.Panel()
        btn_panel.BackgroundColor = COL_BG
        btn_panel.Height = 32
        btn_panel.Content = btn_row
        layout.AddRow(btn_panel)

        self.Content = layout

    def on_select_curve(self, sender, e):
        self.Visible = False
        try:
            ids = rs.GetObjects(
                message="Select a polyline curve to send",
                filter=rs.filter.curve,
                preselect=True,
            )
            if ids:
                self.selected_curve_ids = list(ids)
                self.lbl_curve_status.Text = "{0} curve(s) selected.".format(len(ids))
            else:
                self.selected_curve_ids = []
                self.lbl_curve_status.Text = "No curve selected."
        finally:
            self.Visible = True

    def on_send(self, sender, e):
        email     = self.txt_email.Text.strip()
        password  = self.txt_password.Text
        name      = self.txt_name.Text.strip()
        is_closed = bool(self.chk_closed.Checked)

        if not email or not password:
            self.lbl_status.Text = "Email and password are required."
            return
        if not name:
            self.lbl_status.Text = "Please enter an A-Line name."
            return
        if not self.selected_curve_ids:
            self.lbl_status.Text = "No curve selected."
            return

        obj = sc.doc.Objects.FindId(self.selected_curve_ids[0])
        curve = coerce_curve(obj) if obj else None
        if curve is None:
            self.lbl_status.Text = "Selected object is not a valid curve."
            return

        pts, err = extract_2d_points(curve, is_closed)
        if err:
            self.lbl_status.Text = err
            return

        self.lbl_status.Text = "Sending..."
        self.btn_send.Enabled = False

        captured = {
            "email": email, "password": password,
            "name": name, "is_closed": is_closed, "pts": pts,
        }

        def do_send():
            try:
                token = login(captured["email"], captured["password"])
                aline = create_aline(token, captured["name"], captured["is_closed"], captured["pts"])
                msg = "Created: id={0}  name={1}  points={2}".format(
                    aline.get("id"), aline.get("name"), len(captured["pts"])
                )
            except RuntimeError as ex:
                msg = "Error: " + str(ex)

            def update_ui():
                self.lbl_status.Text = msg
                self.btn_send.Enabled = True

            Rhino.RhinoApp.InvokeOnUiThread(System.Action(update_ui))

        t = threading.Thread(target=do_send)
        t.daemon = True
        t.start()

    def on_close(self, sender, e):
        self.Close()


def main():
    dialog = ALineSenderDialog()
    main_win = Rhino.UI.RhinoEtoApp.MainWindow
    dialog.Owner = main_win
    dialog.Location = drawing.Point(
        main_win.Location.X + 60,
        main_win.Location.Y + 60,
    )
    dialog.Show()


if __name__ == "__main__":
    main()
