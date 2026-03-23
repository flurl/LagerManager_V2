from django.urls import path

from .views import ImportRunView

urlpatterns = [
    path('import/run/', ImportRunView.as_view(), name='import-run'),
]
