
from flask import Flask, request, jsonify, session, redirect, render_template_string
from config import FLASK_PASSWORD, set_forward_status, ENABLE_FORWARD, ADMIN_TELEGRAM_ID
import os

app = Flask(__name__)
app.secret_key = "super-secret-key"

@app.route("/", methods=["GET", "POST"])
def index():
    if "logged_in" not in session:
        return redirect("/login")
    status = ENABLE_FORWARD()
    return render_template_string("""
        <h2>Forwarding is {{ 'ON' if status else 'OFF' }}</h2>
        <form method="post" action="/toggle">
            <button type="submit">{{ 'Tắt' if status else 'Bật' }}</button>
        </form>
        <p><a href="/logs">Xem log forwarding</a></p>
    """, status=status)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == FLASK_PASSWORD:
            session["logged_in"] = True
            return redirect("/")
    return '<form method="post"><input name="password" type="password"/><input type="submit"/></form>'

@app.route("/toggle", methods=["POST"])
def toggle():
    if "logged_in" not in session:
        return redirect("/login")
    set_forward_status(not ENABLE_FORWARD())
    return redirect("/")

@app.route("/logs")
def logs():
    if "logged_in" not in session:
        return redirect("/login")
    try:
        with open("logs/forward.log") as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "Chưa có log."
    return f"<pre>{log_content}</pre>"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "No JSON", 400

    sender_id = int(data.get("sender_id", 0))
    message = data.get("message", "").lower()

    if sender_id != ADMIN_TELEGRAM_ID:
        return jsonify({"status": "unauthorized"}), 403

    if "bật" in message:
        set_forward_status(True)
        return jsonify({"status": "forwarding ON"})
    elif "tắt" in message:
        set_forward_status(False)
        return jsonify({"status": "forwarding OFF"})

    return jsonify({"status": "no command matched"})
