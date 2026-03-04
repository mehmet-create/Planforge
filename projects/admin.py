from django.contrib import admin
from .models import Project

# Register your models here.
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display    = ("name", "organization", "status", "created_by", "created_at")
    list_filter     = ("status", "organization")
    search_fields   = ("name", "organization__name", "created_by__username")
    readonly_fields = ("created_at", "updated_at")