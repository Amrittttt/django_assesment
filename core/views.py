from django.db.models import Count, Sum
from django.http import JsonResponse

from .models import Order


def order_summary_broken(request):
    orders = Order.objects.order_by('-created_at')

    payload = []
    for order in orders:
        payload.append(
            {
                'order_id': order.id,
                'customer_email': order.customer.email,
                'item_count': order.items.count(),
                'total_cents': order.total_cents,
            }
        )

    return JsonResponse({'count': len(payload), 'orders': payload[:50]})


def order_summary_fixed(request):
    orders = (
        Order.objects.select_related('customer')
        .prefetch_related('items')
        .annotate(item_count=Count('items'))
        .order_by('-created_at')
    )

    payload = [
        {
            'order_id': order.id,
            'customer_email': order.customer.email,
            'item_count': order.item_count,
            'total_cents': order.total_cents,
        }
        for order in orders
    ]

    total_revenue = orders.aggregate(total=Sum('total_cents'))['total'] or 0
    return JsonResponse({'count': len(payload), 'total_revenue': total_revenue, 'orders': payload[:50]})
