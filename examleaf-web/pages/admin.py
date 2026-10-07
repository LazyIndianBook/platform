from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Page


@admin.register(Page)
class PageAdmin(SimpleHistoryAdmin):
    list_display = ["title", "slug", "version", "updated"]
    readonly_fields = ["slug", "updated"]
    fields = ["title", "slug", "version", "body_md", "updated"]

    def has_add_permission(self, request):  # the pages are fixed (each has its URL); they are edited, not added
        return False

    def has_delete_permission(self, request, obj=None):
        return False
