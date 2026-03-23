from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('core.urls')),
    path('api/', include('articles.urls')),
    path('api/', include('inventory.urls')),
    path('api/', include('deliveries.urls')),
    path('api/', include('pos_import.urls')),
    path('api/', include('reports.urls')),
]
