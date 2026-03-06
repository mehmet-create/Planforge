"""
Management command: cleanup_blueprints
=======================================
Deletes incomplete/failed Blueprint records that are older than a configurable
threshold (default: 1 hour). These are blueprints where the AI call errored
or the user abandoned the page mid-generation — they never got is_complete=True
and will never be shown to users, but accumulate in the DB indefinitely.

USAGE
-----
Run manually:
    python manage.py cleanup_blueprints

Run for a specific org only:
    python manage.py cleanup_blueprints --org-id 42

Dry run (shows what would be deleted without deleting anything):
    python manage.py cleanup_blueprints --dry-run

SCHEDULING (choose one)
-----------------------
Option A — System cron (simplest, no Celery needed yet):
    # /etc/cron.d/planforge
    0 * * * * deploy /path/to/venv/bin/python /path/to/manage.py cleanup_blueprints >> /var/log/planforge/cleanup.log 2>&1

Option B — Celery Beat (preferred once Celery is added):
    CELERY_BEAT_SCHEDULE = {
        "cleanup-blueprints": {
            "task": "blueprints.tasks.cleanup_failed_blueprints_all_orgs",
            "schedule": crontab(minute=0),   # every hour
        },
    }
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from blueprints.models import Blueprint
from organizations.models import Organization

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete incomplete/failed Blueprint records older than --older-than-hours (default: 1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=1,
            help="Delete incomplete blueprints created more than N hours ago (default: 1).",
        )
        parser.add_argument(
            "--org-id",
            type=int,
            default=None,
            help="Restrict cleanup to a single organization ID (optional).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting anything.",
        )

    def handle(self, *args, **options):
        hours      = options["older_than_hours"]
        org_id     = options["org_id"]
        dry_run    = options["dry_run"]
        cutoff     = timezone.now() - timedelta(hours=hours)

        qs = Blueprint.objects.filter(
            is_complete=False,
            created_at__lt=cutoff,
        )

        if org_id is not None:
            if not Organization.objects.filter(pk=org_id).exists():
                raise CommandError(f"Organization with id={org_id} does not exist.")
            qs = qs.filter(organization_id=org_id)

        count = qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to clean up."))
            return

        scope = f"org_id={org_id}" if org_id else "all organizations"
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {count} incomplete blueprint(s) "
                    f"older than {hours}h for {scope}."
                )
            )
            return

        deleted, _ = qs.delete()
        msg = f"Deleted {deleted} incomplete blueprint(s) older than {hours}h for {scope}."
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)