from django.db import models
from django.contrib.auth.models import User
from organizations.models import Organization

# Create your models here.

# Project — a unit of work that belongs to an Organization.
#
# Design decisions:
# - Projects belong to ONE organization (no cross-org projects for now)
# - created_by is SET_NULL so projects survive if their creator leaves
# - Status is a controlled vocabulary (TextChoices) not a free-text field

class Project(models.Model):

    class Status(models.TextChoices):
        ACTIVE    = "active",    "Active"
        ON_HOLD   = "on_hold",   "On Hold"
        COMPLETED = "completed", "Completed"
        ARCHIVED  = "archived",  "Archived"

    name = models.CharField(max_length=200)

    description = models.TextField(blank=True, default="")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects"
    )

    # Who created the project inside the org.
    # SET_NULL — if they leave, the project stays.
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Project"
        verbose_name_plural = "Projects"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"

    # Convenience status-check properties
    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_archived(self):
        return self.status == self.Status.ARCHIVED