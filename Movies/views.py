import razorpay
import uuid
import os
import json
import hmac
import hashlib
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from datetime import timedelta
from .models import Movie, Theater, Seat, Booking, SeatReservation, Payment
from Movies.utils import get_youtube_embed_url
from .payment_utils import (
    get_razorpay_client,
    generate_idempotency_key,
    create_razorpay_order,
    verify_payment_signature
)

TICKET_PRICE = 200

def movie_list(request):
    search_query = request.GET.get('search')
    if search_query:
        movies = Movie.objects.filter(name__icontains=search_query)
    else:
        movies = Movie.objects.all()
    return render(request, 'movies/movie_list.html', {'movies': movies})

def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theater = Theater.objects.filter(movie=movie)
    return render(request, 'movies/theater_list.html', {'movie': movie, 'theaters': theater})

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
                        id=seat_id,
                        theater=theaters
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

        # Show confirmation page before payment
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
            request.user.id,
            theater_id,
            selected_seats
        )

        existing_payment = Payment.objects.filter(
            idempotency_key=idempotency_key,
            status='success'
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
            # Show exact error instead of redirecting
            return render(request, 'movies/seat_selection.html', {
                'theaters': theaters,
                'seats': Seat.objects.filter(theater=theaters),
                'error': f"EXACT ERROR: {str(e)}"
            })

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

@login_required(login_url='/login/')
def payment_success(request):
    if request.method == 'POST':
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_signature = request.POST.get('razorpay_signature')

        try:
            payment = Payment.objects.get(razorpay_order_id=razorpay_order_id)
        except Payment.DoesNotExist:
            messages.error(request, "Payment record not found!")
            return redirect('home')

        is_valid = verify_payment_signature(
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature
        )

        if not is_valid:
            payment.status = 'failed'
            payment.save()
            messages.error(request, "Payment verification failed!")
            return redirect('home')

        if payment.status == 'success':
            messages.info(request, "Payment already processed!")
            return redirect('profile')

        try:
            with transaction.atomic():
                for seat_id in payment.seats_data:
                    seat = Seat.objects.select_for_update().get(id=seat_id)
                    if seat.is_booked:
                        continue
                    booking = Booking.objects.create(
                        user=request.user,
                        seat=seat,
                        movie=payment.theater.movie,
                        theater=payment.theater,
                    )
                    seat.is_booked = True
                    seat.save()
                    if not payment.booking:
                        payment.booking = booking

                payment.razorpay_payment_id = razorpay_payment_id
                payment.razorpay_signature = razorpay_signature
                payment.status = 'success'
                payment.save()

                SeatReservation.objects.filter(
                    seat_id__in=payment.seats_data
                ).delete()

        except Exception as e:
            payment.status = 'failed'
            payment.save()
            messages.error(request, f"Booking failed: {str(e)}")
            return redirect('home')

        messages.success(request, "Payment successful! Seats booked!")
        return redirect('profile')

    return redirect('home')


def payment_failed(request):
    razorpay_order_id = request.GET.get('order_id')
    if razorpay_order_id:
        Payment.objects.filter(
            razorpay_order_id=razorpay_order_id
        ).update(status='failed')
    messages.error(request, "Payment failed! Please try again.")
    return redirect('home')


@csrf_exempt
def razorpay_webhook(request):
    if request.method == 'POST':
        webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
        webhook_signature = request.headers.get('X-Razorpay-Signature', '')
        body = request.body
        generated_signature = hmac.new(
            webhook_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, webhook_signature):
            return HttpResponse(status=400)

        payload = json.loads(body)
        event = payload.get('event')

        if event == 'payment.captured':
            order_id = payload['payload']['payment']['entity']['order_id']
            payment_id = payload['payload']['payment']['entity']['id']
            payment = Payment.objects.filter(razorpay_order_id=order_id).first()
            if payment and payment.status != 'success':
                payment.razorpay_payment_id = payment_id
                payment.status = 'success'
                payment.save()

        elif event == 'payment.failed':
            order_id = payload['payload']['payment']['entity']['order_id']
            Payment.objects.filter(
                razorpay_order_id=order_id
            ).update(status='failed')

        return HttpResponse(status=200)

    return HttpResponse(status=405)