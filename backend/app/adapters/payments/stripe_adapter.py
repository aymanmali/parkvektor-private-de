import uuid

import stripe

from app.adapters.payments.base import CheckoutInitResult, PaymentProvider


class StripePaymentProvider(PaymentProvider):
    """Production German/EU Stripe Checkout adapter (Cards, SEPA Direct Debit, PayPal, Apple/Google Pay)."""

    def __init__(self, secret_key: str) -> None:
        self.secret_key = secret_key
        stripe.api_key = secret_key

    def create_checkout(
        self,
        *,
        payment_id: str,
        session_id: str,
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        locale: str = "de",
    ) -> CheckoutInitResult:
        checkout = stripe.checkout.Session.create(
            mode="payment",
            locale="de" if locale == "de" else "en",
            payment_method_types=["card", "sepa_debit", "paypal"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_cents,
                        "product_data": {"name": description},
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "payment_id": payment_id,
                "parking_session_id": session_id,
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return CheckoutInitResult(
            provider="stripe",
            provider_ref=checkout.id,
            checkout_url=checkout.url or success_url,
            requires_mock_confirm=False,
        )


class MockPaymentProvider(PaymentProvider):
    """Local zero-key payment adapter mirroring Stripe Checkout flow for dev, demos, and CI."""

    def __init__(self, frontend_base_url: str) -> None:
        self.frontend_base_url = frontend_base_url.rstrip("/")

    def create_checkout(
        self,
        *,
        payment_id: str,
        session_id: str,
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        locale: str = "de",
    ) -> CheckoutInitResult:
        ref = f"mock_cs_{uuid.uuid4().hex[:16]}"
        return CheckoutInitResult(
            provider="mock",
            provider_ref=ref,
            checkout_url=f"{self.frontend_base_url}/{locale}/pay?mock_payment_id={payment_id}",
            requires_mock_confirm=True,
        )
