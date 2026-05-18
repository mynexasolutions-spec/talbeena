"""
app.py — Application factory for Talbeena.
"""
import os
from flask import Flask, render_template, session
from dotenv import load_dotenv

load_dotenv()

from extensions import csrf, limiter, handle_csrf_error
from helpers import register_jinja
import db


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    
    # Payload limit: 16MB
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    # Session configuration
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400
    
    # CSRF configuration
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    
    # Initialize extensions
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Register CSRF error handler
    app.register_error_handler(400, handle_csrf_error)
    
    # Register Jinja2 helpers and globals
    register_jinja(app)
    
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

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)

    # Admin routes (plain endpoint names — no blueprint prefix needed)
    from routes.admin import register as reg_admin
    reg_admin(app)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app


app = create_app()

import os as _os
# Only run migrations in the main process (not the watchdog reloader child).
# This prevents the timeout warning you see on every hot-reload.
if _os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    try:
        db.migrate()
    except Exception as _e:
        print(f"[db.migrate] {_e}")

if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    app.run(debug=debug, port=port, host="0.0.0.0")
