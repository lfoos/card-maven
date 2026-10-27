"""WSGI entry point: ``gunicorn card_maven_api.wsgi:app``."""

from card_maven_api.app import create_app

app = create_app()
