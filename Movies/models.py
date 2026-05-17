from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
import re

def validate_youtube_url(value):
    if not value:
        return
    pattern = r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11}$'
    if not re.match(pattern, value):
        raise ValidationError('Enter a valid YouTube URL.')

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return self.name

class Language(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    def __str__(self):
        return self.name

class Movie(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    image = models.ImageField(upload_to="movies/")
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True, validators=[validate_youtube_url])
    genres = models.ManyToManyField(Genre, blank=True, related_name='movies')
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='movies',
        db_index=True
    )

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['rating']),
            models.Index(fields=['language']),
        ]

    def __str__(self):
        return self.name

class Theater(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters')
    time = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['time']),
            models.Index(fields=['movie']),
        ]

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'

class Seat(models.Model):
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'

class SeatReservation(models.Model):
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE, related_name='reservation')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reserved_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f'Reservation by {self.user.username} for {self.seat.seat_number}'

class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE)
    booked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)

    class Meta:
        indexes = [
            models.Index(fields=['booked_at']),
            models.Index(fields=['movie']),
            models.Index(fields=['theater']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    booking = models.OneToOneField(
        'Booking', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='payment'
    )
    razorpay_order_id = models.CharField(max_length=255, unique=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=500, blank=True, null=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, null=True)
    seats_data = models.JSONField(default=list)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'Payment {self.razorpay_order_id} - {self.status}'