
from django.db import models

from .managers import TenantManager


class Tenant(models.Model):
    name = models.CharField(max_length=128)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.slug


class Customer(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    email = models.EmailField()


class Order(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_cents = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        base_manager_name = 'objects'
        default_manager_name = 'objects'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)


class FailedEmailJob(models.Model):
    recipient = models.EmailField()
    payload = models.JSONField(default=dict)
    error = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
