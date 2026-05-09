from django.contrib import admin

from .models import Draft, Page, Run


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "spent_usd", "budget_usd", "created")


@admin.register(Draft)
class DraftAdmin(admin.ModelAdmin):
    list_display = ("url", "status", "cost_usd", "reviewed_by")
    list_filter = ("status", "run")
    search_fields = ("url", "title")


admin.site.register(Page)
