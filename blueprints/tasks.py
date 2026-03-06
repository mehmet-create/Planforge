"""
Celery tasks — DORMANT on Render's 512 MB plan.

Blueprint generation uses daemon threads instead (see blueprints/views.py).
This file is kept so upgrading to Celery later is a one-line change.

TO ACTIVATE: see planforge/celery.py for full instructions.
"""
# from celery import shared_task
# from .services import run_blueprint_generation
#
# @shared_task(bind=True, max_retries=2, default_retry_delay=10, acks_late=True)
# def generate_blueprint_task(self, blueprint_id: int) -> None:
#     from .services import ServiceError
#     try:
#         run_blueprint_generation(blueprint_id)
#     except ServiceError:
#         pass  # already recorded on the Blueprint row
#     except Exception as exc:
#         raise self.retry(exc=exc)
#
# @shared_task(name="blueprints.tasks.cleanup_failed_blueprints_all_orgs")
# def cleanup_failed_blueprints_all_orgs() -> None:
#     from django.utils import timezone
#     from datetime import timedelta
#     from .models import Blueprint
#     cutoff = timezone.now() - timedelta(hours=1)
#     count, _ = Blueprint.objects.filter(is_complete=False, created_at__lt=cutoff).delete()
#     if count:
#         import logging
#         logging.getLogger(__name__).info("Cleaned up %s failed blueprints", count)