"""Generate Alembic migration."""
import os
os.environ['FLASK_APP'] = 'app.py'
from dotenv import load_dotenv
load_dotenv()

from flask import current_app
from app import create_app
from flask.cli import ScriptInfo
from flask_migrate import upgrade, migrate

app = create_app()
with app.app_context():
    migrate(message="initial models")
    print("Migration script generated!")
