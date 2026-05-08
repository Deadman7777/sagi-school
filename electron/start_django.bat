@echo off
set DJANGO_SETTINGS_MODULE=config.settings.production
set PYTHONUNBUFFERED=1
cd /d "%~dp0..\backend"
python -m waitress --host=127.0.0.1 --port=8765 config.wsgi:application
