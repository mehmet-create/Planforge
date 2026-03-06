"""
Celery application — DORMANT on Render's 512 MB plan.

Blueprint generation currently uses daemon threads instead (zero extra RAM).
This file is kept so upgrading to Celery later requires minimal changes.

TO ACTIVATE:
  1. pip install celery[redis]
  2. Uncomment the import in planforge/__init__.py
  3. Add CELERY_BROKER_URL etc. back to settings/base.py
  4. Deploy a Render Background Worker service:
       celery -A planforge worker --loglevel=info --concurrency=2
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "planforge.settings.prod")

app = Celery("planforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()