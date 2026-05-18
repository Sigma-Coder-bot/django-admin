from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, ExtractHour
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta


def get_revenue_analytics():
    cache_key = 'analytics_revenue'
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = timezone.now()

    from .models import Payment

    daily = list(
        Payment.objects.filter(
            status='success',
            created_at__gte=now - timedelta(days=7)
        ).annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('day')
    )

    weekly = list(
        Payment.objects.filter(
            status='success',
            created_at__gte=now - timedelta(weeks=4)
        ).annotate(week=TruncWeek('created_at'))
        .values('week')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('week')
    )

    monthly = list(
        Payment.objects.filter(
            status='success',
            created_at__gte=now - timedelta(days=180)
        ).annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('month')
    )

    total = Payment.objects.filter(
        status='success'
    ).aggregate(total=Sum('amount'), count=Count('id'))

    result = {
        'daily': daily,
        'weekly': weekly,
        'monthly': monthly,
        'total': total,
    }

    cache.set(cache_key, result, 300)
    return result


def get_popular_movies():
    cache_key = 'analytics_popular_movies'
    cached = cache.get(cache_key)
    if cached:
        return cached

    from .models import Movie

    result = list(
        Movie.objects.annotate(
            booking_count=Count('booking'),
            total_revenue=Sum('booking__price')
        ).order_by('-booking_count')
        .values('name', 'booking_count', 'total_revenue', 'rating')[:10]
    )

    cache.set(cache_key, result, 300)
    return result


def get_busiest_theaters():
    cache_key = 'analytics_busiest_theaters'
    cached = cache.get(cache_key)
    if cached:
        return cached

    from .models import Theater

    theaters = list(
        Theater.objects.select_related('movie').annotate(
            total_seats=Count('seats'),
            booked_seats=Count('seats', filter=Q(seats__is_booked=True)),
        ).order_by('-booked_seats')[:10]
    )

    result = []
    for t in theaters:
        rate = round((t.booked_seats / t.total_seats * 100), 1) if t.total_seats > 0 else 0
        result.append({
            'name': t.name,
            'movie': t.movie.name,
            'total_seats': t.total_seats,
            'booked_seats': t.booked_seats,
            'occupancy_rate': rate,
        })

    cache.set(cache_key, result, 300)
    return result


def get_peak_booking_hours():
    cache_key = 'analytics_peak_hours'
    cached = cache.get(cache_key)
    if cached:
        return cached

    from .models import Booking

    result = list(
        Booking.objects.annotate(hour=ExtractHour('booked_at'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )

    cache.set(cache_key, result, 300)
    return result


def get_cancellation_stats():
    cache_key = 'analytics_cancellation'
    cached = cache.get(cache_key)
    if cached:
        return cached

    from .models import Payment

    total = Payment.objects.count()
    success = Payment.objects.filter(status='success').count()
    failed = Payment.objects.filter(status='failed').count()
    cancelled = Payment.objects.filter(status='cancelled').count()
    pending = Payment.objects.filter(status='pending').count()

    result = {
        'total': total,
        'success': success,
        'failed': failed,
        'cancelled': cancelled,
        'pending': pending,
        'success_rate': round(success / total * 100, 1) if total > 0 else 0,
        'failure_rate': round(failed / total * 100, 1) if total > 0 else 0,
        'cancellation_rate': round(cancelled / total * 100, 1) if total > 0 else 0,
    }

    cache.set(cache_key, result, 300)
    return result


def get_dashboard_summary():
    from django.contrib.auth.models import User
    from .models import Booking

    return {
        'revenue': get_revenue_analytics(),
        'popular_movies': get_popular_movies(),
        'busiest_theaters': get_busiest_theaters(),
        'peak_hours': get_peak_booking_hours(),
        'cancellation_stats': get_cancellation_stats(),
        'total_users': User.objects.count(),
        'total_bookings': Booking.objects.count(),
    }