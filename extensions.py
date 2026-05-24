from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

csrf = CSRFProtect()
db_sql = SQLAlchemy()
migrate = Migrate()

limiter = Limiter(
    get_remote_address,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
)


# Optional: Custom CSRF error handler can be added here if needed
def handle_csrf_error(e):
    return f"CSRF validation failed: {e.description}", 400
