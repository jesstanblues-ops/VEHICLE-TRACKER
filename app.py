# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os, requests, json
from datetime import datetime, date, timedelta
import psycopg2
import psycopg2.extras
from apscheduler.schedulers.background import BackgroundScheduler

import config

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-secret")

# -------------------------
# Database helper
# -------------------------
def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable missing")
    conn = psycopg2.connect(db_url, sslmode="require", cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

# -------------------------
# Initialize DB / seed sample data
# -------------------------
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fleet_items (
        id SERIAL PRIMARY KEY,
        company TEXT,
        category TEXT,
        type TEXT,
        code TEXT,
        model TEXT,
        plate_no TEXT,
        serial_no TEXT,
        current_location TEXT,
        driver TEXT,
        permit_expiry DATE,
        puspakom_expiry DATE,
        insurance_expiry DATE,
        loan_due_date DATE,
        loan_monthly_amount NUMERIC,
        status TEXT,
        remarks TEXT,
        created_on TIMESTAMP DEFAULT NOW()
    );
    """)
    conn.commit()

    # seed sample employees/items if empty
    cur.execute("SELECT COUNT(*) AS c FROM fleet_items")
    if cur.fetchone()["c"] == 0:
        samples = config.SAMPLE_ITEMS
        for s in samples:
            cur.execute("""
            INSERT INTO fleet_items
            (company, category, type, code, model, plate_no, serial_no, current_location, driver,
             permit_expiry, puspakom_expiry, insurance_expiry, loan_due_date, loan_monthly_amount, status, remarks)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                s.get("company"), s.get("category"), s.get("type"), s.get("code"), s.get("model"),
                s.get("plate_no"), s.get("serial_no"), s.get("current_location"), s.get("driver"),
                s.get("permit_expiry"), s.get("puspakom_expiry"), s.get("insurance_expiry"),
                s.get("loan_due_date"), s.get("loan_monthly_amount"), s.get("status"), s.get("remarks")
            ))
        conn.commit()
    cur.close()
    conn.close()

# -------------------------
# Brevo email helper
# -------------------------
def send_email(subject, body, to_email):
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        app.logger.info("BREVO_API_KEY not set; skipping email.")
        return False
    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"name": "Fleet Tracker", "email": os.environ.get("SENDER_EMAIL", config.PLACEHOLDER_SENDER)},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p>"
    }
    headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        app.logger.info("Brevo response: %s %s", r.status_code, r.text)
        return r.status_code in (200,201)
    except Exception as e:
        app.logger.error("send_email error: %s", e)
        return False

# -------------------------
# Monthly report job (runs daily; sends once-per-month)
# -------------------------
def monthly_report_job():
    """
    Runs daily. When it's the 1st of the month (server timezone),
    it sends a report for items that have expiry next month.
    """
    try:
        today = date.today()
        if today.day != 1:
            return  # only run on day 1

        conn = get_db()
        cur = conn.cursor()
        # window: next 30 days (starting today)
        start = today
        end = today + timedelta(days=30)
        cur.execute("""
            SELECT * FROM fleet_items
            WHERE (insurance_expiry BETWEEN %s AND %s)
               OR (puspakom_expiry BETWEEN %s AND %s)
               OR (permit_expiry BETWEEN %s AND %s)
            ORDER BY insurance_expiry NULLS LAST
        """, (start, end, start, end, start, end))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            app.logger.info("Monthly report: nothing to report")
            return

        # build HTML report
        html = "<h3>Fleet items with expiries in next 30 days</h3><table border='1' cellpadding='6'><tr><th>Company</th><th>Code</th><th>Type</th><th>Insurance</th><th>Puspakom</th><th>Permit</th></tr>"
        for r in rows:
            html += f"<tr><td>{r['company']}</td><td>{r['code']}</td><td>{r['type']}</td><td>{r.get('insurance_expiry') or ''}</td><td>{r.get('puspakom_expiry') or ''}</td><td>{r.get('permit_expiry') or ''}</td></tr>"
        html += "</table>"

        recipient = os.environ.get("REPORT_EMAIL", config.DEFAULT_REPORT_EMAIL)
        send_email("Monthly Fleet Expiry Report", html, recipient)

    except Exception as e:
        app.logger.error("monthly_report_job error: %s", e)

# start scheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(monthly_report_job, "interval", days=1, next_run_time=datetime.now())
scheduler.start()

# -------------------------
# Flask routes
# -------------------------
@app.route("/")
def home():
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    # Option 2 premium view: stats and grouped lists
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT company, COUNT(*) as total FROM fleet_items GROUP BY company ORDER BY company")
    by_company = cur.fetchall()
    cur.execute("SELECT category, COUNT(*) as total FROM fleet_items GROUP BY category")
    by_category = cur.fetchall()

    # items flagged: expired or expiring within 30 days
    today = date.today()
    soon = today + timedelta(days=30)
    cur.execute("""
        SELECT * FROM fleet_items
        WHERE (insurance_expiry <= %s AND insurance_expiry IS NOT NULL)
           OR (puspakom_expiry <= %s AND puspakom_expiry IS NOT NULL)
           OR (permit_expiry <= %s AND permit_expiry IS NOT NULL)
        ORDER BY insurance_expiry NULLS LAST
        LIMIT 200
    """, (soon, soon, soon))
    flagged = cur.fetchall()

    cur.execute("SELECT * FROM fleet_items ORDER BY company, type, code LIMIT 500")
    all_items = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("dashboard.html", by_company=by_company, by_category=by_category, flagged=flagged, items=all_items)

@app.route("/item/new", methods=["GET","POST"])
def new_item():
    if request.method == "POST":
        data = {k: request.form.get(k) for k in ["company","category","type","code","model","plate_no","serial_no","current_location","driver","permit_expiry","puspakom_expiry","insurance_expiry","loan_due_date","loan_monthly_amount","status","remarks"]}
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fleet_items (company,category,type,code,model,plate_no,serial_no,current_location,driver,permit_expiry,puspakom_expiry,insurance_expiry,loan_due_date,loan_monthly_amount,status,remarks)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, tuple(data.values()))
        conn.commit()
        cur.close()
        conn.close()
        flash("Item added", "success")
        return redirect(url_for("dashboard"))
    return render_template("item_form.html", item=None, companies=config.COMPANIES, categories=config.CATEGORIES)

@app.route("/item/<int:item_id>/edit", methods=["GET","POST"])
def edit_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        data = {k: request.form.get(k) for k in ["company","category","type","code","model","plate_no","serial_no","current_location","driver","permit_expiry","puspakom_expiry","insurance_expiry","loan_due_date","loan_monthly_amount","status","remarks"]}
        cur.execute("""
            UPDATE fleet_items SET company=%s, category=%s, type=%s, code=%s, model=%s, plate_no=%s, serial_no=%s, current_location=%s, driver=%s,
             permit_expiry=%s, puspakom_expiry=%s, insurance_expiry=%s, loan_due_date=%s, loan_monthly_amount=%s, status=%s, remarks=%s
            WHERE id=%s
        """, tuple(list(data.values()) + [item_id]))
        conn.commit()
        flash("Item updated", "success")
        cur.close()
        conn.close()
        return redirect(url_for("dashboard"))

    cur.execute("SELECT * FROM fleet_items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("item_form.html", item=item, companies=config.COMPANIES, categories=config.CATEGORIES)

@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM fleet_items WHERE id=%s", (item_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Item removed", "info")
    return redirect(url_for("dashboard"))

@app.route("/export_excel")
def export_excel():
    # returns CSV for simplicity
    import io, csv
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM fleet_items ORDER BY company, type, code")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    headers = rows[0].keys() if rows else ["no_data"]
    cw.writerow(headers)
    for r in rows:
        cw.writerow([r.get(h) for h in headers])
    output = si.getvalue()
    return app.response_class(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=fleet_items.csv"})

# test endpoint
@app.route("/test_email")
def test_email():
    ok = send_email("Test Fleet Email", "Hello from Fleet Tracker", os.environ.get("REPORT_EMAIL", config.DEFAULT_REPORT_EMAIL))
    return f"Sent: {ok}"

# -------------------------
# Boot
# -------------------------
with app.app_context():
    init_db()

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0")
