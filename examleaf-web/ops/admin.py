from django.contrib import admin

admin.site.index_template = "admin/dashboard.html"  # the app list with today's and the month's numbers above it
admin.site.site_header = admin.site.site_title = "ExamLeaf admin"
