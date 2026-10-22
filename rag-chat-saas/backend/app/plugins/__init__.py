"""Optional HTTP capability plugins. Public chat never discovers service tools."""
import json
import os
from pathlib import Path


def install(app):
    from . import models  # register isolated tables before database.create_all
    from .api import blueprint
    from .images import blueprint as images_blueprint
    filename = os.getenv('SERVICE_PLUGINS_CONFIG', '')
    app.config.setdefault('PLUGIN_CONFIG', json.loads(Path(filename).read_text('utf-8')) if filename else {})
    app.register_blueprint(blueprint)
    app.register_blueprint(images_blueprint)
    from .runs import install_worker
    install_worker(app)
