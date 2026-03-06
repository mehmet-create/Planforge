from django.urls import path
from . import views

app_name = "blueprints"

urlpatterns = [
    path("", views.blueprint_list, name="list"),
    path("generate/<uuid:project_uuid>/", views.blueprint_generate, name="generate"),
    path("<uuid:blueprint_uuid>/", views.blueprint_detail, name="detail"),
    path("<uuid:blueprint_uuid>/pending/", views.blueprint_pending, name="pending"),
     path("<uuid:blueprint_uuid>/stream/", views.blueprint_stream, name="stream"),
    path("<uuid:blueprint_uuid>/delete/", views.blueprint_delete, name="delete"),
    path("<uuid:blueprint_uuid>/export/", views.blueprint_export, name="export"),
]