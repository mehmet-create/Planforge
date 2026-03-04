from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("create/", views.project_create, name="create"),
    path("<uuid:project_uuid>/", views.project_detail, name="detail"),
    path("<uuid:project_uuid>/edit/", views.project_edit, name="edit"),
    path("<uuid:project_uuid>/delete/", views.project_delete, name="delete"),
]