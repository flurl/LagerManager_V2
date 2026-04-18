from django.urls import URLPattern, URLResolver, path

from .views import (
    BulkStaffConsumptionView,
    StaffConsumptionArticleListView,
    StaffConsumptionDepartmentListView,
)

urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "staff-consumption/departments/",
        StaffConsumptionDepartmentListView.as_view(),
        name="staff-consumption-departments",
    ),
    path(
        "staff-consumption/articles/",
        StaffConsumptionArticleListView.as_view(),
        name="staff-consumption-articles",
    ),
    path(
        "staff-consumption/entries/bulk/",
        BulkStaffConsumptionView.as_view(),
        name="staff-consumption-bulk",
    ),
]
