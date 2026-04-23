
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from .tenant_context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    def for_current_tenant(self):
        tenant = get_current_tenant()
        if tenant is None:
            raise ImproperlyConfigured('Tenant context is not set for this request.')
        return self.filter(tenant=tenant)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        return super().get_queryset().for_current_tenant()
