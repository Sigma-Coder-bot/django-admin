import razorpay
from django.conf import settings

import os
import json
import hmac
import hashlib
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.core.cache import cache
from datetime import timedelta
from .models import Movie, Theater, Seat, Booking, SeatReservation, Payment, Genre, Language
from Movies.utils import get_youtube_embed_url
from .payment_utils import (
    get_razorpay_client,
    generate_idempotency_key,
    create_razorpay_order,
    verify_payment_signature
)
from .analytics import get_dashboard_summary

TICKET_PRICE = 30
TICKET_PRICE = 50
TICKET_PRICE = 70

def movie_list(request):
    search_query = request.GET.get('search', '')
    selected_genres = request.GET.getlist('genre')
    selected_languages = request.GET.getlist('language')
    sort_by = request.GET.get('sort', 'name')
    page_number = request.GET.get('page', 1)

    # Optimized base queryset — avoids N+1 queries
    movies = Movie.objects.select_related('language').prefetch_related('genres')

    # Search filter using Q objects — avoids full table scan
    if search_query:
        movies = movies.filter(
            Q(name__icontains=search_query) |
            Q(cast__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Multi-select genre filter
    if selected_genres:
        movies = movies.filter(
            genres__id__in=selected_genres
        ).distinct()

    # Multi-select language filter
    if selected_languages:
        movies = movies.filter(language__id__in=selected_languages)

    # Sorting
    sort_map = {
        'name': 'name',
        'rating': '-rating',
        'newest': '-id',
        'oldest': 'id',
    }
    movies = movies.order_by(sort_map.get(sort_by, 'name'))

    # Dynamic filter counts — DB level aggregation
    genre_counts = Genre.objects.filter(
        movies__in=movies
    ).annotate(count=Count('movies', distinct=True)).order_by('name')

    language_counts = Language.objects.filter(
        movies__in=movies
    ).annotate(count=Count('movies', distinct=True)).order_by('name')

    # Pagination — 12 per page
    paginator = Paginator(movies, 12)
    page_obj = paginator.get_page(page_number)

    all_genres = Genre.objects.all()
    all_languages = Language.objects.all()

    return render(request, 'movies/movie_list.html', {
        'movies': page_obj,
        'page_obj': page_obj,
        'all_genres': all_genres,
        'all_languages': all_languages,
        'genre_counts': {g.id: g.count for g in genre_counts},
        'language_counts': {l.id: l.count for l in language_counts},
        'selected_genres': [int(g) for g in selected_genres],
        'selected_languages': [int(l) for l in selected_languages],
        'search_query': search_query,
        'sort_by': sort_by,
        'total_count': paginator.count,
        'sort_options': [
            ('name', 'Name A-Z'),
            ('rating', 'Top Rated'),
            ('newest', 'Newest'),
            ('oldest', 'Oldest'),
        ],
    })

def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theater = Theater.objects.filter(movie=movie)
    return render(request, 'movies/theater_list.html', {
        'movie': movie,
        'theaters': theater
    })


def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    embed_url = get_youtube_embed_url(movie.trailer_url)
    return render(request, 'movies/movie_detail.html', {
        'movie': movie,
        'embed_url': embed_url,
    })


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    theaters = get_object_or_404(Theater, id=theater_id)
    SeatReservation.objects.filter(expires_at__lt=timezone.now()).delete()
    seats = Seat.objects.filter(theater=theaters)

    if request.method == 'POST':
        selected_seats = request.POST.getlist('seats')
        error_seats = []

        if not selected_seats:
            return render(request, "movies/seat_selection.html", {
                'theaters': theaters,
                "seats": seats,
                'error': "No seat selected"
            })

        try:
            with transaction.atomic():
                for seat_id in selected_seats:
                    seat = Seat.objects.select_for_update().get(
                        id=seat_id, theater=theaters
                    )
                    if seat.is_booked:
                        error_seats.append(seat.seat_number)
                        continue
                    try:
                        existing = SeatReservation.objects.get(seat=seat)
                        if not existing.is_expired() and existing.user != request.user:
                            error_seats.append(f"{seat.seat_number} (reserved)")
                            continue
                        else:
                            existing.delete()
                    except SeatReservation.DoesNotExist:
                        pass

                    SeatReservation.objects.create(
                        seat=seat,
                        user=request.user,
                        expires_at=timezone.now() + timedelta(minutes=2)
                    )

                if error_seats:
                    error_message = f"These seats are unavailable: {', '.join(error_seats)}"
                    return render(request, 'movies/seat_selection.html', {
                        'theaters': theaters,
                        "seats": seats,
                        'error': error_message
                    })

        except Exception as e:
            return render(request, 'movies/seat_selection.html', {
                'theaters': theaters,
                "seats": seats,
                'error': f"Booking failed: {str(e)}"
            })

        return render(request, 'movies/confirm_seats.html', {
            'theaters': theaters,
            'selected_seats': selected_seats,
            'seats_info': [Seat.objects.get(id=s) for s in selected_seats],
            'total_amount': TICKET_PRICE * len(selected_seats),
        })

    return render(request, 'movies/seat_selection.html', {
        'theaters': theaters,
        "seats": seats
    })


@login_required(login_url='/login/')
def initiate_payment(request, theater_id):
    theaters = get_object_or_404(Theater, id=theater_id)

    if request.method == 'POST':
        selected_seats = request.POST.getlist('seats')

        if not selected_seats:
            messages.error(request, "No seats selected!")
            return redirect('book_seats', theater_id=theater_id)

        idempotency_key = generate_idempotency_key(
            request.user.id, theater_id, selected_seats
        )

        existing_payment = Payment.objects.filter(
            idempotency_key=idempotency_key, status='success'
        ).first()

        if existing_payment:
            messages.warning(request, "You have already booked these seats!")
            return redirect('profile')

        total_amount = TICKET_PRICE * len(selected_seats)

        try:
            order = create_razorpay_order(total_amount, idempotency_key)
            payment, created = Payment.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults={
                    'user': request.user,
                    'razorpay_order_id': order['id'],
                    'amount': total_amount,
                    'status': 'pending',
                    'theater': theaters,
                    'seats_data': selected_seats,
                }
            )
            if not created:
                payment.razorpay_order_id = order['id']
                payment.save()

        except Exception as e:
            messages.error(request, f"Payment initiation failed: {str(e)}")
            return redirect('book_seats', theater_id=theater_id)

        return render(request, 'movies/payment.html', {
            'theaters': theaters,
            'selected_seats': selected_seats,
            'total_amount': total_amount,
            'razorpay_order_id': order['id'],
            'razorpay_key_id': os.environ.get('RAZORPAY_KEY_ID'),
            'payment': payment,
            'user': request.user,
        })

    return redirect('book_seats', theater_id=theater_id)


@csrf_exempt
def payment_success(request):

    if request.method == "POST":

        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_signature = request.POST.get('razorpay_signature')

        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }

        try:
            # VERIFY PAYMENT SIGNATURE
            client.utility.verify_payment_signature(params_dict)

        except razorpay.errors.SignatureVerificationError:

            Payment.objects.filter(
                razorpay_order_id=razorpay_order_id
            ).update(status='failed')

            messages.error(request, "Payment verification failed.")
            return redirect('home')

        # PAYMENT VERIFIED
        payment = Payment.objects.filter(
            razorpay_order_id=razorpay_order_id
        ).first()

        if payment and payment.status != 'success':

            payment.status = 'success'
            payment.razorpay_payment_id = razorpay_payment_id
            payment.save()

            # CREATE BOOKINGS HERE

        messages.success(request, "Payment successful!")
        return redirect('home')


def payment_failed(request):
    razorpay_order_id = request.GET.get('order_id')

    if razorpay_order_id:
        payment = Payment.objects.filter(
            razorpay_order_id=razorpay_order_id
        ).first()

        if payment:
            payment.status = 'failed'
            payment.save()

            # Release reserved seats immediately
            SeatReservation.objects.filter(
                seat_id__in=payment.seats_data
            ).delete()

    messages.error(request, "Payment failed! Please try again.")
    return redirect('home')


@csrf_exempt
def razorpay_webhook(request):

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    received_signature = request.headers.get('X-Razorpay-Signature')

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    body = request.body.decode('utf-8')

    try:
        client.utility.verify_webhook_signature(
            body,
            received_signature,
            webhook_secret
        )

    except razorpay.errors.SignatureVerificationError:
        return HttpResponse(status=400)

    payload = json.loads(body)

    event = payload.get('event')

    if event == 'payment.captured':

        razorpay_order_id = payload['payload']['payment']['entity']['order_id']

        payment = Payment.objects.filter(
            razorpay_order_id=razorpay_order_id
        ).first()

        # IDEMPOTENCY PROTECTION
        if payment and payment.status != 'success':

            payment.status = 'success'
            payment.save()

    return HttpResponse(status=200)


@staff_member_required
def admin_dashboard(request):
    if request.GET.get('refresh'):
        cache.clear()
    data = get_dashboard_summary()
    return render(request, 'movies/admin_dashboard.html', {
        'data': data,
        'user': request.user,
    })