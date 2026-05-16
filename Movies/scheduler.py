from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone

def release_expired_reservations():
    """Auto-releases expired seat reservations every minute"""
    from Movies.models import SeatReservation
    expired = SeatReservation.objects.filter(expires_at__lt=timezone.now())
    count = expired.count()
    expired.delete()
    if count > 0:
        print(f"Released {count} expired seat reservations")

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")
    scheduler.add_job(
        release_expired_reservations,
        'interval',
        minutes=1,
        name='release_expired_reservations',
        jobstore='default',
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started — checking expired reservations every minute")