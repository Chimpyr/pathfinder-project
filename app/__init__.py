from flask import Flask
from config import Config

def create_app(config_class=Config):
    """
    Application factory function.
    
    Creates and configures the Flask application with all blueprints.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register main routes blueprint
    from app.routes import main
    app.register_blueprint(main)
    
    # Register async task polling blueprint
    from app.blueprints.tasks import tasks_bp
    app.register_blueprint(tasks_bp)
    
    # Register admin blueprint
    from app.blueprints.admin import admin_bp
    app.register_blueprint(admin_bp)

    return app

