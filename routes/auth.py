import uuid
import bcrypt
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import db
from extensions import limiter
from authlib.integrations.flask_client import OAuth
import os
from email_utils import send_password_reset_email, send_welcome_email, create_password_reset_otp, verify_password_reset_otp

bp = Blueprint("auth", __name__)

oauth = OAuth()
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if "user" in session:
        return redirect(url_for("public.index"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")
        try:
            user = db.query_one(
                "SELECT id, first_name, last_name, email, password_hash, role FROM users WHERE email=?",
                [email]
            )
        except Exception as e:
            flash(f"Database error: {e}", "error")
            return render_template("login.html")
        if not user or not bcrypt.checkpw(
            password[:72].encode("utf-8"),
            user.get("password_hash", "").encode("utf-8")
        ):
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
        session["user"] = {
            "id":    str(user["id"]),
            "name":  full_name,
            "email": user["email"],
            "role":  user.get("role", "customer"),
        }
        flash(f"Welcome back, {full_name}!", "success")
        next_url = request.args.get("next") or request.form.get("next")
        if next_url:
            return redirect(next_url)
        if user.get("role") in ("admin", "manager"):
            try:
                return redirect(url_for("admin_dashboard"))
            except Exception:
                return redirect("/admin")
        return redirect(url_for("public.index"))
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if "user" in session:
        return redirect(url_for("public.index"))
    if request.method == "POST":
        fname    = request.form.get("first_name", "").strip()
        lname    = request.form.get("last_name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        name     = f"{fname} {lname}".strip()
        if not all([fname, email, password]):
            flash("All fields are required.", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")
        try:
            if db.query_one("SELECT id FROM users WHERE email=?", [email]):
                flash("An account with that email already exists.", "error")
                return render_template("register.html")
            hashed   = bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            new_user = db.execute_returning(
                "INSERT INTO users (id, first_name, last_name, email, password_hash, role) "
                "VALUES (?,?,?,?,?,'customer') RETURNING id, first_name, last_name, email, role",
                [str(uuid.uuid4()), fname, lname, email, hashed]
            )
            if new_user:
                session["user"] = {
                    "id":    str(new_user["id"]),
                    "name":  f"{new_user['first_name']} {new_user.get('last_name','')}".strip(),
                    "email": new_user["email"],
                    "role":  "customer",
                }
                flash(f"Welcome to Talbeena, {name}!", "success")
                return redirect(url_for("public.index"))
        except Exception as e:
            flash(f"Registration failed: {e}", "error")
    return render_template("register.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.index"))


# ── Account & Addresses ────────────────────────────────────────────────────────

@bp.route("/account", methods=["GET", "POST"])
def account():
    if "user" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("auth.login", next=request.url))
    uid = session["user"]["id"]
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "update_profile":
            fname = request.form.get("first_name", "").strip()
            lname = request.form.get("last_name", "").strip()
            if not fname:
                flash("First name is required.", "error")
            else:
                try:
                    db.execute("UPDATE users SET first_name=?, last_name=? WHERE id=?", [fname, lname, uid])
                    session["user"]["name"] = f"{fname} {lname}".strip()
                    flash("Profile updated successfully.", "success")
                except Exception as e:
                    flash(f"Error updating profile: {e}", "error")
        elif action == "add_address":
            try:
                is_default = 1 if request.form.get("is_default") == "on" else 0
                if is_default:
                    db.execute("UPDATE user_addresses SET is_default=0 WHERE user_id=?", [uid])
                db.execute(
                    """INSERT INTO user_addresses
                       (id, user_id, label, first_name, last_name, phone,
                        address_line1, address_line2, city, state, pincode, country, is_default)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [
                        str(uuid.uuid4()), uid,
                        request.form.get("label", "Home"),
                        request.form.get("first_name", ""),
                        request.form.get("last_name", ""),
                        request.form.get("phone", ""),
                        request.form.get("address_line1", ""),
                        request.form.get("address_line2", ""),
                        request.form.get("city", ""),
                        request.form.get("state", ""),
                        request.form.get("pincode", ""),
                        request.form.get("country", "India"),
                        is_default,
                    ]
                )
                flash("Address added successfully.", "success")
            except Exception as e:
                flash(f"Error saving address: {e}", "error")
        return redirect(url_for("auth.account"))
    try:
        user      = db.query_one(
            "SELECT id, first_name, last_name, email, role, created_at FROM users WHERE id=?", [uid]
        )
        addresses = db.query(
            "SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC", [uid]
        )
        orders    = db.query(
            "SELECT id, created_at, total_amount, status, payment_method, payment_status "
            "FROM orders WHERE user_id=? ORDER BY created_at DESC",
            [uid]
        )
    except Exception as e:
        user = session["user"]
        addresses = []
        orders    = []
        flash(f"Error loading account data: {e}", "error")
    return render_template("account.html", user=user, addresses=addresses, orders=orders)


@bp.route("/account/address/<addr_id>/delete", methods=["POST"])
def account_address_delete(addr_id):
    if "user" not in session:
        return redirect(url_for("auth.login"))
    db.execute(
        "DELETE FROM user_addresses WHERE id=? AND user_id=?",
        [addr_id, session["user"]["id"]]
    )
    flash("Address removed.", "success")
    return redirect(url_for("auth.account"))


@bp.route("/account/address/<addr_id>/default", methods=["POST"])
def account_address_default(addr_id):
    if "user" not in session:
        return redirect(url_for("auth.login"))
    uid = session["user"]["id"]
    db.execute("UPDATE user_addresses SET is_default=0 WHERE user_id=?", [uid])
    db.execute("UPDATE user_addresses SET is_default=1 WHERE id=? AND user_id=?", [addr_id, uid])
    flash("Default address updated.", "success")
    return redirect(url_for("auth.account"))


# ── Google OAuth ────────────────────────────────────────────────────────

@bp.route("/auth/google")
def auth_google():
    redirect_uri = url_for("auth.auth_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@bp.route("/auth/google/callback")
def auth_google_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo') or google.parse_id_token(token)

        if not user_info:
            flash("Failed to get user info from Google.", "error")
            return redirect(url_for("auth.login"))

        google_id = user_info.get('sub')
        email = user_info.get('email', '').lower()
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')

        if not email or not google_id:
            flash("Invalid user information from Google.", "error")
            return redirect(url_for("auth.login"))

        # Check if user exists with this Google ID
        user = db.query_one(
            "SELECT id, first_name, last_name, email, role FROM users WHERE google_id=?",
            [google_id]
        )

        if user:
            # Existing Google user - log them in
            full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
            session["user"] = {
                "id": str(user["id"]),
                "name": full_name,
                "email": user["email"],
                "role": user.get("role", "customer"),
            }
            flash(f"Welcome back, {full_name}!", "success")
            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            if user.get("role") in ("admin", "manager"):
                try:
                    return redirect(url_for("admin_dashboard"))
                except Exception:
                    return redirect("/admin")
            return redirect(url_for("public.index"))

        # Check if email already exists (from password login)
        existing_user = db.query_one(
            "SELECT id FROM users WHERE email=?",
            [email]
        )

        if existing_user:
            # Email exists but no Google ID - update to add Google ID
            db.execute(
                "UPDATE users SET google_id=? WHERE email=?",
                [google_id, email]
            )
            user = db.query_one(
                "SELECT id, first_name, last_name, email, role FROM users WHERE email=?",
                [email]
            )
        else:
            # New user - create account
            user_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO users (id, first_name, last_name, email, google_id, role) VALUES (?,?,?,?,?,'customer')",
                [user_id, first_name, last_name, email, google_id]
            )
            user = {
                "id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "role": "customer"
            }

        # Log the user in
        full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
        session["user"] = {
            "id": str(user["id"]),
            "name": full_name,
            "email": user["email"],
            "role": user.get("role", "customer"),
        }
        flash(f"Welcome to Talbeena, {full_name}!", "success")
        return redirect(url_for("public.index"))

    except Exception as e:
        flash(f"Google login failed: {str(e)}", "error")
        return redirect(url_for("auth.login"))


# ── Password Reset ──────────────────────────────────────────────────────

@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Email is required.", "error")
            return render_template("forgot_password.html")

        try:
            user = db.query_one(
                "SELECT id, first_name, last_name FROM users WHERE email=?",
                [email]
            )

            if not user:
                flash("If that email address is in our system, you'll receive password reset instructions.", "info")
                return render_template("forgot_password.html")

            otp = create_password_reset_otp(user["id"])
            if otp and send_password_reset_email(email, user.get("first_name", ""), otp):
                session["reset_user_id"] = str(user["id"])
                session["reset_email"] = email
                flash("Check your email for the OTP to reset your password.", "success")
                return redirect(url_for("auth.verify_otp"))
            else:
                flash("Failed to send email. Please try again.", "error")
        except Exception as e:
            flash(f"Error: {str(e)}", "error")

        return render_template("forgot_password.html")

    return render_template("forgot_password.html")


@bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "reset_user_id" not in session:
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        if not otp:
            flash("OTP is required.", "error")
            return render_template("verify_otp.html")

        try:
            user_id = session.get("reset_user_id")
            if verify_password_reset_otp(user_id, otp):
                session["otp_verified"] = True
                flash("OTP verified! Now set your new password.", "success")
                return redirect(url_for("auth.reset_password"))
            else:
                flash("Invalid or expired OTP.", "error")
        except Exception as e:
            flash(f"Error: {str(e)}", "error")

        return render_template("verify_otp.html")

    return render_template("verify_otp.html")


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "reset_user_id" not in session or not session.get("otp_verified"):
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not password or not confirm:
            flash("All fields are required.", "error")
            return render_template("reset_password.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("reset_password.html")

        try:
            user_id = session.get("reset_user_id")
            hashed = bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            db.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                [hashed, user_id]
            )

            session.pop("reset_user_id", None)
            session.pop("reset_email", None)
            session.pop("otp_verified", None)

            flash("Your password has been reset successfully! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash(f"Error: {str(e)}", "error")

    return render_template("reset_password.html")
