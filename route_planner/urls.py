from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/api/health/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/", include("planner.urls")),
]
