from django.urls import path

from .views import RoutePlanView, health_check

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("route-plan/", RoutePlanView.as_view(), name="route-plan"),
]
