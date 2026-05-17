from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def release_expired_reservations():
    """Auto-releases expired seat reservations every minute"""
    try:
        from Movies.models import SeatReservation
        expired = SeatReservation.objects.filter(expires_at__lt=timezone.now())
        count = expired.count()
        expired.delete()
        if count > 0:
            logger.info(f"Released {count} expired seat reservations")
    except Exception as e:
        logger.error(f"Error releasing reservations: {e}")

def start():
    try:
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
        logger.info("Scheduler started")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {e}")