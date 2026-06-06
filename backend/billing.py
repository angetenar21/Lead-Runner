"""
Stripe Billing Module — uses Stripe Checkout Sessions (test mode).

Flow:
1. User clicks "Upgrade to Pro" → frontend calls POST /api/billing/create-checkout
2. Backend creates a Stripe Checkout Session → returns the session URL
3. Frontend redirects the user to Stripe's hosted checkout page
4. User enters test card (4242 4242 4242 4242) and pays
5. Stripe redirects back to our app with ?session_id=...
6. Frontend calls POST /api/billing/verify-session to confirm payment
7. Backend verifies with Stripe API → upgrades user to Pro

All in test mode — $0 real charges, but fully production-grade architecture.
"""

import os
import stripe
from dotenv import load_dotenv

load_dotenv()

# Initialize Stripe with test secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# The price ID for the Pro plan — created in Stripe Dashboard (test mode)
PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")

# Frontend URL for redirects
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def create_checkout_session(user_id: int, user_email: str) -> dict:
    """
    Creates a Stripe Checkout Session for upgrading to Pro.
    Returns the checkout URL to redirect the user to.
    """
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": PRO_PRICE_ID,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{FRONTEND_URL}/dashboard?upgrade=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/dashboard?upgrade=cancelled",
            customer_email=user_email,
            metadata={
                "user_id": str(user_id),
            },
            # Allow promotion codes for demo purposes
            allow_promotion_codes=True,
        )
        return {
            "session_id": session.id,
            "url": session.url,
        }
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")


def verify_checkout_session(session_id: str) -> dict:
    """
    Verifies a completed Stripe Checkout Session.
    Returns user_id and payment status.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status == "paid":
            return {
                "paid": True,
                "user_id": int(session.metadata.get("user_id", 0)),
                "customer_email": session.customer_email,
                "subscription_id": session.subscription,
                "stripe_customer_id": session.customer,
            }
        else:
            return {
                "paid": False,
                "user_id": int(session.metadata.get("user_id", 0)),
                "status": session.payment_status,
            }
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe verification error: {str(e)}")


def create_billing_portal_session(stripe_customer_id: str) -> str:
    """
    Creates a Stripe Customer Portal session for managing subscriptions.
    Returns the portal URL.
    """
    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=f"{FRONTEND_URL}/dashboard",
        )
        return session.url
    except stripe.error.StripeError as e:
        raise Exception(f"Stripe portal error: {str(e)}")
