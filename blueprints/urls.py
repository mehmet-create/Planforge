from django.urls import path
from . import views

app_name = "blueprints"

urlpatterns = [
    path("", views.blueprint_list, name="list"),
    path("generate/<int:project_id>/", views.blueprint_generate, name="generate"),
    path("<uuid:blueprint_uuid>/", views.blueprint_detail, name="detail"),
    path("<uuid:blueprint_uuid>/delete/", views.blueprint_delete, name="delete"),
    path("<uuid:blueprint_uuid>/export/", views.blueprint_export, name="export"),
]