import razorpay
import hmac
import hashlib
import os

def get_razorpay_client():
    key_id = os.environ.get('rzp_test_SqBAfb0AZJpYSy')
    key_secret = os.environ.get('9A3UpojB7PcHQ2xgFi3qjlI7')
    return razorpay.Client(auth=(key_id, key_secret))

def generate_idempotency_key(user_id, theater_id, seat_ids):
    """Generate unique key to prevent duplicate transactions"""
    raw = f"{user_id}-{theater_id}-{'-'.join(map(str, sorted(seat_ids)))}"
    return hashlib.md5(raw.encode()).hexdigest()

def create_razorpay_order(amount_rupees, idempotency_key):
    """Create order on Razorpay — amount in paise"""
    client = get_razorpay_client()
    amount_paise = int(amount_rupees * 100)
    order = client.order.create({
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': idempotency_key[:40],
        'payment_capture': 1
    })
    return order

def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify payment signature server-side.
    Prevents fraud and replay attacks.
    """
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    generated_signature = hmac.new(
        key_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated_signature, razorpay_signature)