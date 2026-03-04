from django.urls import path
from . import views

app_name = "organizations"

urlpatterns = [
    path("", views.org_list, name="list"),
    path("create/", views.org_create, name="create"),
    path("<slug:org_slug>/switch/", views.org_switch, name="switch"),
    path("<slug:org_slug>/settings/", views.org_settings, name="settings"),
    path("<slug:org_slug>/update/", views.org_update, name="update"),
    path("<slug:org_slug>/delete/", views.org_delete, name="delete"),
    path("<slug:org_slug>/members/invite/", views.org_invite_member, name="invite_member"),
    path("<slug:org_slug>/members/<uuid:membership_uuid>/remove/", views.org_remove_member, name="remove_member"),
    path("<slug:org_slug>/members/<uuid:membership_uuid>/role/", views.org_change_member_role, name="change_member_role"),
]