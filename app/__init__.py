from flask import Flask
from sqlalchemy import inspect, text

from config import Config


def _ensure_movement_pref_columns(app, db):
    """Best-effort compatibility patch for existing user databases."""
    try:
        inspector = inspect(db.engine)
        if 'users' not in inspector.get_table_names():
            return

        columns = {col['name'] for col in inspector.get_columns('users')}
        statements = []

        if 'preferred_distance_unit' not in columns:
            statements.append(
                "ALTER TABLE users ADD COLUMN preferred_distance_unit VARCHAR(2) NOT NULL DEFAULT 'km'"
            )
        if 'walking_speed_kmh' not in columns:
            statements.append(
                "ALTER TABLE users ADD COLUMN walking_speed_kmh DOUBLE PRECISION NOT NULL DEFAULT 5.0"
            )
        if 'running_easy_speed_kmh' not in columns:
            statements.append(
                "ALTER TABLE users ADD COLUMN running_easy_speed_kmh DOUBLE PRECISION NOT NULL DEFAULT 9.5"
            )
        if 'running_race_speed_kmh' not in columns:
            statements.append(
                "ALTER TABLE users ADD COLUMN running_race_speed_kmh DOUBLE PRECISION NOT NULL DEFAULT 12.5"
            )
        if 'movement_prefs_updated_at' not in columns:
            statements.append(
                "ALTER TABLE users ADD COLUMN movement_prefs_updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            )

        if not statements:
            return

        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()

        app.logger.info(
            "Applied movement preference schema compatibility patch (%d column changes).",
            len(statements),
        )
    except Exception as exc:
        db.session.rollback()
        app.logger.warning(
            "Movement preference schema compatibility patch skipped: %s",
            exc,
        )


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
            _ensure_movement_pref_columns(app, db)
        except Exception:
            app.logger.warning(
                "Could not create user database tables. "
                "PostgreSQL may not be running."
            )

    return app
