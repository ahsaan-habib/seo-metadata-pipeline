from django.contrib import admin
from django.urls import path

from metadata import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("review/<int:run_id>/", views.review, name="review"),
]
