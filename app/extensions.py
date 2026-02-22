"""
Flask Extensions
================
Centralised extension instances to avoid circular imports.

All extensions are instantiated here without an app context,
then initialised in the application factory (create_app).
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# ORM
db = SQLAlchemy()

# Schema migrations
migrate = Migrate()

# Authentication / session management
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
