import logging
import threading
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger('starticket.email')

def send_booking_confirmation_email(
    user_email,
    user_name,
    movie_name,
    theater_name,
    show_time,
    seat_numbers,
    amount,
    payment_id,
    booking_date
):
    """
    Send booking confirmation email with retry logic.
    Runs in background thread to not block API response.
    """
    def send_with_retry(max_retries=3):
        for attempt in range(max_retries):
            try:
                # Render HTML template
                html_content = render_to_string(
                    'emails/booking_confirmation.html',
                    {
                        'user_name': user_name,
                        'movie_name': movie_name,
                        'theater_name': theater_name,
                        'show_time': show_time,
                        'seat_numbers': seat_numbers,
                        'amount': amount,
                        'payment_id': payment_id,  # Only payment ID, not full card details
                        'booking_date': booking_date,
                    }
                )

                # Plain text fallback
                text_content = f"""
Hi {user_name},

Your booking is confirmed!

Movie: {movie_name}
Theater: {theater_name}
Show Time: {show_time}
Seats: {', '.join(seat_numbers)}
Amount Paid: Rs.{amount}
Payment ID: {payment_id}
Booking Date: {booking_date}

Enjoy the movie!
StarTicket Team
                """.strip()

                # Create email
                email = EmailMultiAlternatives(
                    subject=f'Booking Confirmed - {movie_name} | StarTicket',
                    body=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user_email],
                )
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)

                logger.info(f"Email sent successfully to {user_email}")
                return True

            except Exception as e:
                logger.error(
                    f"Email attempt {attempt + 1} failed for {user_email}: {str(e)}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"All {max_retries} email attempts failed for {user_email}. "
                        f"Payment ID: {payment_id}"
                    )
                    return False

    # Run in background thread — does not block booking response
    email_thread = threading.Thread(target=send_with_retry)
    email_thread.daemon = True
    email_thread.start()