"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                     STEM SPLITTER - LICENSING & PAYMENTS                      ║
║                        Stripe Integration + Trial System                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Pricing Model:
- 2 free songs to try (full quality, all features)
- $30 one-time payment for unlimited forever
"""

import os
import secrets
import hashlib
from datetime import datetime
from functools import wraps
from flask import request, jsonify
from flask_sqlalchemy import SQLAlchemy
import stripe

# Initialize SQLAlchemy (will be bound to app later)
db = SQLAlchemy()

# Configuration
FREE_TRIAL_SONGS = 2
PRODUCT_PRICE_USD = 3000  # $30.00 in cents

# Stripe Configuration (set via environment variables)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # Create this in Stripe Dashboard


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class Device(db.Model):
    """
    Track devices by fingerprint.
    Each unique device gets 2 free songs.
    """
    __tablename__ = 'devices'
    
    id = db.Column(db.Integer, primary_key=True)
    fingerprint = db.Column(db.String(64), unique=True, nullable=False, index=True)
    songs_processed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # License association
    license_key = db.Column(db.String(64), db.ForeignKey('licenses.key'), nullable=True)
    license = db.relationship('License', backref='devices')
    
    def __repr__(self):
        return f'<Device {self.fingerprint[:8]}... songs={self.songs_processed}>'
    
    @property
    def is_trial(self):
        return self.license_key is None
    
    @property
    def songs_remaining(self):
        if self.license_key:
            return float('inf')  # Unlimited
        return max(0, FREE_TRIAL_SONGS - self.songs_processed)
    
    @property
    def can_process(self):
        if self.license_key:
            return True
        return self.songs_processed < FREE_TRIAL_SONGS


class License(db.Model):
    """
    License keys for paid users.
    One-time purchase = unlimited forever.
    """
    __tablename__ = 'licenses'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True)
    
    # Stripe info
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_payment_intent = db.Column(db.String(255), nullable=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    activated_at = db.Column(db.DateTime, nullable=True)
    
    # Usage stats
    total_songs_processed = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<License {self.key[:8]}... active={self.is_active}>'
    
    @staticmethod
    def generate_key():
        """Generate a unique license key."""
        raw = secrets.token_hex(16)
        # Format: XXXX-XXXX-XXXX-XXXX
        return '-'.join([raw[i:i+4].upper() for i in range(0, 16, 4)])


class Transaction(db.Model):
    """
    Track all payment transactions.
    """
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), db.ForeignKey('licenses.key'), nullable=False)
    
    # Stripe data
    stripe_session_id = db.Column(db.String(255), unique=True)
    stripe_payment_intent = db.Column(db.String(255))
    stripe_customer_id = db.Column(db.String(255))
    
    # Payment details
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), default='usd')
    status = db.Column(db.String(50), default='pending')  # pending, completed, failed, refunded
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relation
    license = db.relationship('License', backref='transactions')


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_device_fingerprint():
    """
    Generate a device fingerprint from request headers.
    This is a simple implementation - can be enhanced with JS fingerprinting.
    """
    components = [
        request.headers.get('User-Agent', ''),
        request.headers.get('Accept-Language', ''),
        request.headers.get('Accept-Encoding', ''),
        request.remote_addr or '',
    ]
    raw = '|'.join(components)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_create_device():
    """Get existing device or create new one."""
    fingerprint = get_device_fingerprint()
    
    device = Device.query.filter_by(fingerprint=fingerprint).first()
    if not device:
        device = Device(fingerprint=fingerprint)
        db.session.add(device)
        db.session.commit()
    
    return device


def activate_license_for_device(device, license_key):
    """Activate a license key for a device."""
    license = License.query.filter_by(key=license_key, is_active=True).first()
    
    if not license:
        return False, "Invalid or inactive license key"
    
    device.license_key = license_key
    license.activated_at = datetime.utcnow()
    db.session.commit()
    
    return True, "License activated successfully"


# ═══════════════════════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════

def require_processing_rights(f):
    """
    Decorator to check if device can process songs.
    Either has remaining free trials or valid license.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        device = get_or_create_device()
        
        if not device.can_process:
            return jsonify({
                "error": "Trial expired",
                "message": "You've used your 2 free songs. Upgrade to unlimited for $30!",
                "trial_expired": True,
                "songs_processed": device.songs_processed,
                "upgrade_url": "/api/checkout"
            }), 402  # Payment Required
        
        # Inject device into request context
        request.device = device
        return f(*args, **kwargs)
    
    return decorated_function


# ═══════════════════════════════════════════════════════════════════════════════
# STRIPE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def create_checkout_session(success_url, cancel_url):
    """
    Create a Stripe Checkout session for the $30 one-time payment.
    """
    if not stripe.api_key:
        raise ValueError("Stripe API key not configured")
    
    # Generate license key in advance
    license_key = License.generate_key()
    
    # Create license record (pending activation)
    license = License(key=license_key, is_active=False)
    db.session.add(license)
    db.session.commit()
    
    try:
        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'STEM SPLITTER - Unlimited License',
                        'description': 'One-time payment. Unlimited stem separations. Forever.',
                        'images': ['https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/soundcloud.svg'],
                    },
                    'unit_amount': PRODUCT_PRICE_USD,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url + f'?license_key={license_key}&session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=cancel_url,
            metadata={
                'license_key': license_key,
            },
            payment_intent_data={
                'metadata': {
                    'license_key': license_key,
                }
            }
        )
        
        # Create transaction record
        transaction = Transaction(
            license_key=license_key,
            stripe_session_id=session.id,
            amount_cents=PRODUCT_PRICE_USD,
            status='pending'
        )
        db.session.add(transaction)
        db.session.commit()
        
        return session
    
    except stripe.error.StripeError as e:
        # Clean up on error
        db.session.delete(license)
        db.session.commit()
        raise e


def handle_successful_payment(session_id):
    """
    Handle successful payment - activate the license.
    Called by webhook or success page verification.
    """
    transaction = Transaction.query.filter_by(stripe_session_id=session_id).first()
    
    if not transaction:
        return False, "Transaction not found"
    
    if transaction.status == 'completed':
        return True, transaction.license_key  # Already processed
    
    # Verify with Stripe
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            # Activate license
            license = transaction.license
            license.is_active = True
            license.stripe_customer_id = session.customer
            license.email = session.customer_details.email if session.customer_details else None
            
            # Update transaction
            transaction.status = 'completed'
            transaction.completed_at = datetime.utcnow()
            transaction.stripe_customer_id = session.customer
            
            if session.payment_intent:
                transaction.stripe_payment_intent = session.payment_intent
                license.stripe_payment_intent = session.payment_intent
            
            db.session.commit()
            
            return True, license.key
    
    except stripe.error.StripeError as e:
        return False, str(e)
    
    return False, "Payment not completed"


def process_webhook_event(payload, sig_header):
    """
    Process Stripe webhook events.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("Stripe webhook secret not configured")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise ValueError("Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session['id'])
    
    elif event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        license_key = payment_intent.get('metadata', {}).get('license_key')
        if license_key:
            license = License.query.filter_by(key=license_key).first()
            if license:
                license.is_active = True
                license.stripe_payment_intent = payment_intent['id']
                db.session.commit()
    
    return event['type']


# ═══════════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════════

def init_licensing(app):
    """Initialize licensing system with Flask app."""
    
    # Configure SQLite database
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///stem_splitter.db')
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
    
    # Initialize database
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
    
    return db


