from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta
from .models import Movie, Theater, Seat, Booking, SeatReservation
from Movies.utils import get_youtube_embed_url

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

    # Auto-release expired reservations before showing seats
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
                    # Row-level locking with select_for_update
                    seat = Seat.objects.select_for_update().get(
                        id=seat_id,
                        theater=theaters
                    )

                    # Check if already booked
                    if seat.is_booked:
                        error_seats.append(seat.seat_number)
                        continue

                    # Check if reserved by another user
                    try:
                        existing = SeatReservation.objects.get(seat=seat)
                        if not existing.is_expired() and existing.user != request.user:
                            error_seats.append(f"{seat.seat_number} (reserved)")
                            continue
                        else:
                            # Expired or same user — delete old reservation
                            existing.delete()
                    except SeatReservation.DoesNotExist:
                        pass

                    # Create 2-minute reservation lock
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

                # Confirm booking — convert reservations to bookings
                for seat_id in selected_seats:
                    seat = Seat.objects.select_for_update().get(id=seat_id)
                    if not seat.is_booked:
                        Booking.objects.create(
                            user=request.user,
                            seat=seat,
                            movie=theaters.movie,
                            theater=theaters
                        )
                        seat.is_booked = True
                        seat.save()
                        # Remove reservation after booking confirmed
                        SeatReservation.objects.filter(seat=seat).delete()

        except Exception as e:
            return render(request, 'movies/seat_selection.html', {
                'theaters': theaters,
                "seats": seats,
                'error': f"Booking failed: {str(e)}"
            })

        messages.success(request, "Seats booked successfully!")
        return redirect('profile')

    return render(request, 'movies/seat_selection.html', {
        'theaters': theaters,
        "seats": seats
    })