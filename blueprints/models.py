from django.db import models
import logging
from django.contrib.auth.models import User
from organizations.models import Organization
from projects.models import Project
import uuid
# Create your models here.

logger = logging.getLogger(__name__)


class Blueprint(models.Model):
    """
    A single AI-generated project blueprint.
    Linked to a project and org. Stores the prompt and
    the full structured result from Gemini as JSON.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="blueprints"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="blueprints"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="blueprints"
    )
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # What the user described / asked for
    prompt = models.TextField()

    # Gemini's structured response — stored as JSON
    # Shape: { overview, cost_breakdown[], timeline[], recommendations[], total_min, total_max }
    result = models.JSONField(default=dict)

    # True once Gemini responded successfully
    is_complete = models.BooleanField(default=False, db_index=True)

    # If generation failed, store the error for debugging
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Blueprint"
        verbose_name_plural = "Blueprints"
        ordering            = ["-created_at"]
        indexes = [
            # get_project_blueprints() and get_org_blueprints() both filter on
            # (organization_id, is_complete=True). A standalone is_complete index
            # can't satisfy that — Postgres would still scan all org rows.
            # This composite index makes those queries instant at any scale.
            models.Index(fields=["organization", "is_complete"], name="blueprint_org_complete_idx"),
        ]

    def __str__(self):
        return f"Blueprint for {self.project.name} — {self.created_at:%Y-%m-%d}"

    @property
    def total_range(self):
        if not self.result:
            return None
        low  = self.result.get("total_min")
        high = self.result.get("total_max")
        if low is None or high is None:
            return None
        currency = self.project.currency or "USD"
        return f"{currency} {low:,.0f} – {high:,.0f}"


class BlueprintMessage(models.Model):
    """
    A single turn in the blueprint conversation.
    Stored so the user can re-read the full exchange later.
    """

    class Role(models.TextChoices):
        USER      = "user",      "User"
        ASSISTANT = "assistant", "Assistant"

    blueprint = models.ForeignKey(
        Blueprint,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    role    = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} — {self.blueprint.project.name}"