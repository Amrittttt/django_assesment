from django.http import HttpResponseBadRequest

from .models import Tenant
from .tenant_context import reset_current_tenant, set_current_tenant


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = self._resolve_tenant(request)
        if tenant is None:
            return HttpResponseBadRequest('Tenant not provided or invalid.')

        token = set_current_tenant(tenant)
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant(token)

    def _resolve_tenant(self, request):
        tenant_id = request.headers.get('X-Tenant-ID')
        if tenant_id:
            return Tenant.objects.filter(id=tenant_id).first()

        host = request.get_host().split(':')[0]
        if host.count('.') >= 2:
            subdomain = host.split('.')[0]
            return Tenant.objects.filter(slug=subdomain).first()
        return None

