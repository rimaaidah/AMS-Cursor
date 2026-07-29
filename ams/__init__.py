from pathlib import Path

from flask import Flask


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        static_folder=str(base_dir / "static"),
        template_folder=str(base_dir / "templates"),
    )
    app.config["SECRET_KEY"] = "dev-secret-change-me"

    from .routes import register_routes

    register_routes(app)
    return app

