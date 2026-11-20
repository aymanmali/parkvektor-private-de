from app.adapters.payments.base import PaymentProvider
from app.adapters.payments.stripe_adapter import MockPaymentProvider, StripePaymentProvider
from app.core.config import get_settings


def get_payment_provider() -> PaymentProvider:
    settings = get_settings()
    if settings.payment_provider == "stripe" and settings.stripe_secret_key:
        return StripePaymentProvider(settings.stripe_secret_key)
    return MockPaymentProvider(settings.frontend_base_url)
