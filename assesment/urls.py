
from django.contrib import admin
from django.urls import include, path
from importlib.util import find_spec

from core.views import order_summary_broken, order_summary_fixed

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/orders/summary/broken/', order_summary_broken),
    path('api/orders/summary/fixed/', order_summary_fixed),
]

if find_spec('debug_toolbar') is not None:
    urlpatterns.insert(1, path('__debug__/', include('debug_toolbar.urls')))
