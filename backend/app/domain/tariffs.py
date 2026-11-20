import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.entities import Site, TariffPlan


@dataclass(frozen=True)
class TariffResult:
    duration_minutes: int
    drive_through_free: bool
    is_whitelisted: bool
    free_minutes_applied: int
    validated_minutes_applied: int
    billable_minutes: int
    billable_hours: int
    gross_cents: int
    net_cents: int
    vat_cents: int
    vat_rate_percent: float
    currency: str
    reason_code: str


def split_german_vat(gross_cents: int, vat_rate_bps: int = 1900) -> tuple[int, int]:
    """Decompose German VAT-inclusive gross cents into (net_cents, vat_cents) using standard rounding."""
    if gross_cents <= 0 or vat_rate_bps <= 0:
        return gross_cents, 0
    # gross = net * (1 + vat_rate_bps / 10000)
    net = int(math.floor((gross_cents * 10000) / (10000 + vat_rate_bps) + 0.5))
    vat = gross_cents - net
    return net, vat


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def calculate_tariff(
    *,
    entry_at: datetime,
    exit_at: datetime,
    site: Site,
    plan: TariffPlan,
    is_whitelisted: bool = False,
    validated_minutes: int = 0,
    validated_full_free: bool = False,
) -> TariffResult:
    """
    Barrierless shopping-mall tariff calculator tailored for German timezone & 19% MwSt.:
    - Whitelist & full tenant validation => €0
    - Drive-through grace window (e.g. 15 min) => €0
    - Minute-by-minute weekday vs. weekend evaluation in Europe/Berlin timezone
    - Free allowance (e.g. 240 min Mon-Fri, all-day free Sat-Sun) + tenant bonus minutes
    - Progressive hourly tiers + daily max cap per 24h block
    """
    entry_utc = _ensure_utc(entry_at)
    exit_utc = _ensure_utc(exit_at)
    raw_seconds = max(0.0, (exit_utc - entry_utc).total_seconds())
    duration_minutes = math.ceil(raw_seconds / 60.0) if raw_seconds > 0 else 0
    vat_rate_pct = plan.vat_rate_bps / 100.0

    if is_whitelisted:
        return TariffResult(
            duration_minutes=duration_minutes,
            drive_through_free=False,
            is_whitelisted=True,
            free_minutes_applied=duration_minutes,
            validated_minutes_applied=0,
            billable_minutes=0,
            billable_hours=0,
            gross_cents=0,
            net_cents=0,
            vat_cents=0,
            vat_rate_percent=vat_rate_pct,
            currency=plan.currency,
            reason_code="WHITELISTED",
        )

    if validated_full_free:
        return TariffResult(
            duration_minutes=duration_minutes,
            drive_through_free=False,
            is_whitelisted=False,
            free_minutes_applied=0,
            validated_minutes_applied=duration_minutes,
            billable_minutes=0,
            billable_hours=0,
            gross_cents=0,
            net_cents=0,
            vat_cents=0,
            vat_rate_percent=vat_rate_pct,
            currency=plan.currency,
            reason_code="VALIDATED_FULL_FREE",
        )

    if duration_minutes <= site.drive_through_grace_minutes:
        return TariffResult(
            duration_minutes=duration_minutes,
            drive_through_free=True,
            is_whitelisted=False,
            free_minutes_applied=duration_minutes,
            validated_minutes_applied=0,
            billable_minutes=0,
            billable_hours=0,
            gross_cents=0,
            net_cents=0,
            vat_cents=0,
            vat_rate_percent=vat_rate_pct,
            currency=plan.currency,
            reason_code="DRIVE_THROUGH_GRACE",
        )

    tz = ZoneInfo(site.timezone or "Europe/Berlin")
    local_entry = entry_utc.astimezone(tz)

    # Count billable weekday vs. weekend minutes accurately across midnight / weekend transitions
    weekday_minutes = 0
    weekend_minutes = 0
    cursor = local_entry
    for _ in range(duration_minutes):
        if cursor.weekday() >= 5:  # Saturday=5, Sunday=6
            weekend_minutes += 1
        else:
            weekday_minutes += 1
        cursor += timedelta(minutes=1)

    if plan.weekend_all_day_free:
        free_weekend = weekend_minutes
    else:
        free_weekend = min(weekend_minutes, plan.weekend_free_minutes)

    free_weekday = min(weekday_minutes, plan.weekday_free_minutes)
    total_free_allowance = free_weekday + free_weekend

    remaining_after_free = max(0, duration_minutes - total_free_allowance)
    applied_validation = min(remaining_after_free, max(0, validated_minutes))
    billable_minutes = max(0, remaining_after_free - applied_validation)

    if billable_minutes == 0:
        reason = "WEEKEND_FREE" if (weekend_minutes == duration_minutes and plan.weekend_all_day_free) else "WITHIN_FREE_WINDOW"
        return TariffResult(
            duration_minutes=duration_minutes,
            drive_through_free=False,
            is_whitelisted=False,
            free_minutes_applied=total_free_allowance,
            validated_minutes_applied=applied_validation,
            billable_minutes=0,
            billable_hours=0,
            gross_cents=0,
            net_cents=0,
            vat_cents=0,
            vat_rate_percent=vat_rate_pct,
            currency=plan.currency,
            reason_code=reason,
        )

    billable_hours = math.ceil(billable_minutes / 60.0)
    tiers = plan.hourly_tiers_cents or [300]

    # Charge per 24h day block so daily_max_cents caps each day cleanly
    total_gross = 0
    hours_left = billable_hours
    while hours_left > 0:
        day_hours = min(24, hours_left)
        day_gross = 0
        for h in range(day_hours):
            tier_rate = tiers[h] if h < len(tiers) else tiers[-1]
            day_gross += tier_rate
        if plan.daily_max_cents > 0:
            day_gross = min(day_gross, plan.daily_max_cents)
        total_gross += day_gross
        hours_left -= day_hours

    net_cents, vat_cents = split_german_vat(total_gross, plan.vat_rate_bps)
    return TariffResult(
        duration_minutes=duration_minutes,
        drive_through_free=False,
        is_whitelisted=False,
        free_minutes_applied=total_free_allowance,
        validated_minutes_applied=applied_validation,
        billable_minutes=billable_minutes,
        billable_hours=billable_hours,
        gross_cents=total_gross,
        net_cents=net_cents,
        vat_cents=vat_cents,
        vat_rate_percent=vat_rate_pct,
        currency=plan.currency,
        reason_code="BILLABLE_OVERTIME",
    )
