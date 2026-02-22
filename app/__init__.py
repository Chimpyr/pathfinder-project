from flask import Flask
from config import Config


def create_app(config_class=Config):
    """
    Application factory function.
    
    Creates and configures the Flask application with all blueprints,
    database extensions, and authentication.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Database bootstrap ────────────────────────────────────────────
    # Ensure user_db exists on the PostGIS container before ORM connects.
    # Gracefully skips if PostgreSQL is unreachable (local dev without Docker).
    from scripts.db_bootstrap import ensure_user_db
    ensure_user_db()

    # ── Initialise extensions ─────────────────────────────────────────
    from app.extensions import db, migrate, login_manager
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Return JSON 401 instead of redirect for unauthenticated API requests
    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify
        return jsonify({'error': 'Authentication required'}), 401

    # ── Flask-Login user loader ───────────────────────────────────────
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Register blueprints ───────────────────────────────────────────
    # Core routing
    from app.routes import main
    app.register_blueprint(main)
    
    # Async task polling
    from app.blueprints.tasks import tasks_bp
    app.register_blueprint(tasks_bp)
    
    # Admin panel
    from app.blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    # Authentication
    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    # User data CRUD (pins, routes)
    from app.blueprints.user_data import user_data_bp
    app.register_blueprint(user_data_bp)

    # ── Create tables (development convenience) ───────────────────────
    # In production, use `flask db upgrade` instead.
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            app.logger.warning(
                "Could not create user database tables. "
                "PostgreSQL may not be running."
            )

    return app
