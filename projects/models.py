from django.db import models
from django.contrib.auth.models import User
from organizations.models import Organization
import uuid

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

    class Currency(models.TextChoices):
        USD = "USD", "USD — US Dollar"
        EUR = "EUR", "EUR — Euro"
        GBP = "GBP", "GBP — British Pound"
        CAD = "CAD", "CAD — Canadian Dollar"
        AUD = "AUD", "AUD — Australian Dollar"
        NGN = "NGN", "NGN — Nigerian Naira"
        GHS = "GHS", "GHS — Ghanaian Cedi"
        KES = "KES", "KES — Kenyan Shilling"
        ZAR = "ZAR", "ZAR — South African Rand"  

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )      

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

    budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
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
    
    @property
    def budget_display(self):
        """Human-readable budget string, e.g. 'USD 12,500.00' or 'Not set'."""
        if self.budget is None:
            return "Not set"
        return f"{self.currency} {self.budget:,.2f}"