from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Page


@admin.register(Page)
class PageAdmin(SimpleHistoryAdmin):
    list_display = ["title", "slug", "version", "effective_from", "placeholders_left", "updated"]
    readonly_fields = ["slug", "updated"]
    # a new version with its day and summary; the panel's Policy versions numbers them and publishes for a later day
    fields = ["title", "slug", "version", "effective_from", "summary", "body_md", "updated"]

    @admin.display(description="[placeholders] left")
    def placeholders_left(self, page):
        return len(page.placeholders)

    def has_add_permission(self, request):  # the pages are fixed (each has its URL); they are edited, not added
        return False

    def has_delete_permission(self, request, obj=None):
        return False
