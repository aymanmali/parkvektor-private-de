from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutInitResult:
    provider: str
    provider_ref: str
    checkout_url: str
    requires_mock_confirm: bool = False


class PaymentProvider(ABC):
    @abstractmethod
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
        """Create a hosted checkout session and return provider reference + redirect URL."""
