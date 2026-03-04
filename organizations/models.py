from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import uuid

# Create your models here.

# Organization — the top-level SaaS tenant.
# A user can create or belong to multiple organizations.
#
# Membership — the join table between User and Organization.
# Every user inside an organization has exactly one membership record,
# which carries their role (owner, admin, or member)

class Organization(models.Model):
    # The organization name shown in the UI
    name = models.CharField(max_length=150)

    # URL-safe version of the name — used in routes like /org/acme-corp/
    # Unique so two orgs can't share a URL slug.
    slug = models.SlugField(max_length=160, unique=True, blank=True)

    # Who created this organization — they become the owner automatically.
    # SET_NULL so the org survives if the creator deletes their account.
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_organizations"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Organization"
        verbose_name_plural = "Organizations"
        ordering            = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug from name if not already set.
        # Appends a short unique suffix to prevent collisions
        # e.g. "Acme Corp" → "acme-corp-a1b2"
        if not self.slug:
            base_slug  = slugify(self.name)
            unique_bit = uuid.uuid4().hex[:6]
            self.slug  = f"{base_slug}-{unique_bit}"
        super().save(*args, **kwargs)


class Membership(models.Model):

    class Role(models.TextChoices):
        OWNER  = "owner",  "Owner"
        ADMIN  = "admin",  "Admin"
        MEMBER = "member", "Member"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations"
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Membership"
        verbose_name_plural = "Memberships"
        # A user can only have ONE membership per organization.
        # This is enforced at the database level, not just application level.
        unique_together = ("user", "organization")
        ordering        = ["joined_at"]

    def __str__(self):
        return f"{self.user.username} — {self.organization.name} ({self.role})"

    # Convenience role-check properties
    # Use these in templates and views instead of comparing strings directly.
    # e.g.  {% if membership.is_owner %}  rather than  {% if membership.role == 'owner' %}

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_admin_or_owner(self):
        return self.role in (self.Role.OWNER, self.Role.ADMIN)