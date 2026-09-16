from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import RedirectView
from django.views.static import serve

urlpatterns = [
    path('', include('portal.urls')),
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/portal/logo.png?v=20260916', permanent=False)),
]

urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]