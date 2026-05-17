from django.db.models import (
    Count, Sum, Avg, F, Q,
    ExpressionWrapper, FloatField
)
from django.db.models.functions import (
    TruncDay, TruncWeek, TruncMonth, ExtractHour
)
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from .models import Booking, Payment, Movie, Theater, Seat


def get_revenue_analytics():
    """Get daily, weekly, monthly revenue using DB aggregation"""
    cache_key = 'analytics_revenue'
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = timezone.now()

    # Daily revenue — last 7 days
    daily_revenue = Payment.objects.filter(
        status='success',
        created_at__gte=now - timedelta(days=7)
    ).annotate(
        day=TruncDay('created_at')
    ).values('day').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('day')

    # Weekly revenue — last 4 weeks
    weekly_revenue = Payment.objects.filter(
        status='success',
        created_at__gte=now - timedelta(weeks=4)
    ).annotate(
        week=TruncWeek('created_at')
    ).values('week').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('week')

    # Monthly revenue — last 6 months
    monthly_revenue = Payment.objects.filter(
        status='success',
        created_at__gte=now - timedelta(days=180)
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('month')

    # Total revenue
    total_revenue = Payment.objects.filter(
        status='success'
    ).aggregate(
        total=Sum('amount'),
        count=Count('id')
    )

    result = {
        'daily': list(daily_revenue),
        'weekly': list(weekly_revenue),
        'monthly': list(monthly_revenue),
        'total': total_revenue,
    }

    cache.set(cache_key, result, 300)  # Cache 5 minutes
    return result


def get_popular_movies():
    """Get most popular movies by booking count"""
    cache_key = 'analytics_popular_movies'
    cached = cache.get(cache_key)
    if cached:
        return cached

    movies = Movie.objects.annotate(
        booking_count=Count('booking'),
        total_revenue=Sum('booking__price')
    ).order_by('-booking_count')[:10]

    result = list(movies.values(
        'name', 'booking_count', 'total_revenue', 'rating'
    ))

    cache.set(cache_key, result, 300)
    return result


def get_busiest_theaters():
    """Get busiest theaters by seat occupancy rate"""
    cache_key = 'analytics_busiest_theaters'
    cached = cache.get(cache_key)
    if cached:
        return cached

    theaters = Theater.objects.annotate(
        total_seats=Count('seats'),
        booked_seats=Count('seats', filter=Q(seats__is_booked=True)),
    ).order_by('-booked_seats')[:10]

    result = []
    for theater in theaters:
        occupancy_rate = 0
        if theater.total_seats > 0:
            occupancy_rate = round(
                (theater.booked_seats / theater.total_seats) * 100, 1
            )
        result.append({
            'name': theater.name,
            'movie': theater.movie.name,
            'total_seats': theater.total_seats,
            'booked_seats': theater.booked_seats,
            'occupancy_rate': occupancy_rate,
        })

    cache.set(cache_key, result, 300)
    return result


def get_peak_booking_hours():
    """Get peak booking hours using DB-level aggregation"""
    cache_key = 'analytics_peak_hours'
    cached = cache.get(cache_key)
    if cached:
        return cached

    peak_hours = Booking.objects.annotate(
        hour=ExtractHour('booked_at')
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')

    result = list(peak_hours)
    cache.set(cache_key, result, 300)
    return result


def get_cancellation_stats():
    """Get payment cancellation and failure rates"""
    cache_key = 'analytics_cancellation'
    cached = cache.get(cache_key)
    if cached:
        return cached

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
        'success_rate': round((success / total * 100), 1) if total > 0 else 0,
        'failure_rate': round((failed / total * 100), 1) if total > 0 else 0,
        'cancellation_rate': round((cancelled / total * 100), 1) if total > 0 else 0,
    }

    cache.set(cache_key, result, 300)
    return result


def get_dashboard_summary():
    """Get all analytics for dashboard"""
    return {
        'revenue': get_revenue_analytics(),
        'popular_movies': get_popular_movies(),
        'busiest_theaters': get_busiest_theaters(),
        'peak_hours': get_peak_booking_hours(),
        'cancellation_stats': get_cancellation_stats(),
        'total_users': get_total_users(),
        'total_bookings': Booking.objects.count(),
    }


def get_total_users():
    from django.contrib.auth.models import User
    return User.objects.count()