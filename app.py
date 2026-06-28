"""
app.py — Application factory for Talbeena.
"""
import os
from flask import Flask, render_template, session, request
from dotenv import load_dotenv

load_dotenv()

from extensions import csrf, limiter, handle_csrf_error
from extensions import db_sql, migrate as db_migrate
from helpers import register_jinja
import db
from routes.auth import oauth
from email_utils import mail
from flask_compress import Compress


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    
    # Payload limit: 16MB
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # Production flag
    app.config['PRODUCTION'] = os.getenv("PRODUCTION", "False").lower() == "true"

    # Cache static files for 1 year in production
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000
    
    # SQLAlchemy
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "connect_args": {"connect_timeout": 15},
    }
    db_sql.init_app(app)
    db_migrate.init_app(app, db_sql)
    
    # Session configuration
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400
    
    # CSRF configuration
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    
    # Initialize extensions
    csrf.init_app(app)
    limiter.init_app(app)
    oauth.init_app(app)
    Compress(app)  # Enable gzip compression
    
    # Flask-Mail config
    app.config["MAIL_SERVER"]         = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"]           = int(os.getenv("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"]        = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    app.config["MAIL_USERNAME"]       = os.getenv("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"]       = os.getenv("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "")
    mail.init_app(app)
    
    # Register CSRF error handler
    app.register_error_handler(400, handle_csrf_error)
    
    # Register Jinja2 helpers and globals
    register_jinja(app)
    
    # Cache-Control headers for static assets + Performance optimizations
    @app.after_request
    def set_cache_headers(response):
        # Static assets: cache for 1 year
        if request.path.startswith('/static/'):
            ext = request.path.rsplit('.', 1)[-1].lower()
            if ext in ('webp', 'jpg', 'jpeg', 'png', 'gif', 'svg', 'ico', 'woff', 'woff2', 'js', 'css'):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'

        # Add performance headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'

        return response

    # Session initialization - ensure session exists for CSRF token
    @app.before_request
    def ensure_session():
        session.setdefault('_csrf_initialized', True)

    @app.context_processor
    def inject_globals():
        cart  = session.get("cart", {})
        count = sum(item.get("qty", 0) for item in cart.values())
        return {"cart_count": count, "current_user": session.get("user")}

    # Blueprints
    from routes.public   import bp as public_bp
    from routes.auth     import bp as auth_bp
    from routes.cart     import bp as cart_bp
    from routes.checkout import bp as checkout_bp
    from routes.blog     import bp as blog_bp
    from bigship.routes  import bigship_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(bigship_bp)

    # Admin routes (plain endpoint names — no blueprint prefix needed)
    from routes.admin import register as reg_admin
    reg_admin(app)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    @app.teardown_appcontext
    def close_db_connection(exception):
        """Close database connection pool on app shutdown."""
        try:
            db.close_pool()
        except Exception:
            pass

    return app


app = create_app()

import os as _os
# Only run setup in the main process (not the watchdog reloader child).
if _os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    # Quick check: only migrate if the users table doesn't exist yet
    try:
        conn = db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.users')")
        exists = cur.fetchone()[0]
        conn.close()
        if not exists:
            db.migrate()
    except Exception:
        # If connection fails, try migrate anyway (fresh database)
        try:
            db.migrate()
        except Exception:
            pass

    # ── Auto-create default admin if none exists ──
    try:
        if not db.query_one("SELECT id FROM users WHERE role='admin'"):
            import uuid, bcrypt
            pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            db.execute(
                "INSERT INTO users (id, first_name, last_name, email, password_hash, role) VALUES (%s,%s,%s,%s,%s,%s)",
                [str(uuid.uuid4()), "Admin", "User", "admin@talbeena.com", pw, "admin"]
            )
    except Exception:
        pass

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    app.run(debug=debug, port=port, host="0.0.0.0")
