
from django.contrib import admin

from .models import Customer, FailedEmailJob, Order, OrderItem, Tenant

admin.site.register(Tenant)
admin.site.register(Customer)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(FailedEmailJob)
