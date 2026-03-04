from django.contrib import admin
from django.contrib import admin
from .models import Blueprint, BlueprintMessage

# Register your models here.

class BlueprintMessageInline(admin.TabularInline):
    model  = BlueprintMessage
    extra  = 0
    fields = ("role", "content", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Blueprint)
class BlueprintAdmin(admin.ModelAdmin):
    list_display  = ("project", "organization", "created_by", "is_complete", "created_at")
    list_filter   = ("is_complete", "organization")
    search_fields = ("project__name", "prompt")
    inlines       = [BlueprintMessageInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(BlueprintMessage)
class BlueprintMessageAdmin(admin.ModelAdmin):
    list_display = ("blueprint", "role", "created_at")