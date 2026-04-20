from django.urls import URLPattern, URLResolver, path

from .views import (
    BulkStaffConsumptionView,
    StaffConsumptionArticleListView,
    StaffConsumptionDepartmentListView,
    StaffConsumptionEntriesListView,
    StaffConsumptionGroupedView,
    StaffConsumptionImportCreateView,
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
    path(
        "staff-consumption/entries/grouped/",
        StaffConsumptionGroupedView.as_view(),
        name="staff-consumption-grouped",
    ),
    path(
        "staff-consumption/entries/",
        StaffConsumptionEntriesListView.as_view(),
        name="staff-consumption-entries",
    ),
    path(
        "staff-consumption/import/",
        StaffConsumptionImportCreateView.as_view(),
        name="staff-consumption-import",
    ),
]
