from datetime import UTC, datetime

from app.domain.tariffs import calculate_tariff, split_german_vat
from app.models.entities import Site, TariffPlan


def _make_site_and_plan() -> tuple[Site, TariffPlan]:
    site = Site(
        id="s1",
        organization_id="o1",
        site_code="MUC-TEST",
        name="Test Mall",
        address="Teststr. 1",
        timezone="Europe/Berlin",
        total_spaces=100,
        privacy_notice_url="https://example.de/dsgvo",
        compliant_purge_hours=24,
        paid_purge_hours=24,
        pay_later_grace_hours=48,
        drive_through_grace_minutes=15,
    )
    plan = TariffPlan(
        id="t1",
        site_id="s1",
        name="Mall Premium",
        currency="EUR",
        vat_rate_bps=1900,
        weekday_free_minutes=240,  # 4h Mon-Fri
        weekend_all_day_free=True,
        weekend_free_minutes=1440,
        hourly_tiers_cents=[300, 400, 500],  # 5th hr €3, 6th hr €4, €5/hr after
        daily_max_cents=2500,
        violation_penalty_cents=3500,
    )
    return site, plan


def test_drive_through_grace_is_free():
    site, plan = _make_site_and_plan()
    # Wednesday 10:00 -> 10:14 UTC
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 18, 10, 14, tzinfo=UTC),
        site=site,
        plan=plan,
    )
    assert res.gross_cents == 0
    assert res.drive_through_free is True
    assert res.reason_code == "DRIVE_THROUGH_GRACE"


def test_weekday_within_4h_free_window():
    site, plan = _make_site_and_plan()
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 18, 13, 0, tzinfo=UTC),
        site=site,
        plan=plan,
    )
    assert res.duration_minutes == 240
    assert res.gross_cents == 0
    assert res.reason_code == "WITHIN_FREE_WINDOW"


def test_weekday_progressive_overtime_and_german_vat():
    site, plan = _make_site_and_plan()
    # 5h 35m on Wednesday -> 4h free + 1h35m billable -> 2 billable hrs -> €3 + €4 = €7.00
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 18, 14, 35, tzinfo=UTC),
        site=site,
        plan=plan,
    )
    assert res.billable_hours == 2
    assert res.gross_cents == 700
    assert res.net_cents + res.vat_cents == 700
    assert res.net_cents == 588
    assert res.vat_cents == 112
    assert split_german_vat(-100, 1900) == (0, 0)
    assert split_german_vat(700, 0) == (700, 0)


def test_weekend_all_day_free():
    site, plan = _make_site_and_plan()
    # Saturday 10:00 -> 19:00 CET (UTC+1 in November)
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 21, 9, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 21, 18, 0, tzinfo=UTC),
        site=site,
        plan=plan,
    )
    assert res.gross_cents == 0
    assert res.reason_code == "WEEKEND_FREE"


def test_merchant_validation_reduces_fee():
    site, plan = _make_site_and_plan()
    # 5h 35m weekday with +120 min Cinema validation -> 4h free + 2h cinema = 6h covered => €0
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 18, 14, 35, tzinfo=UTC),
        site=site,
        plan=plan,
        validated_minutes=120,
    )
    assert res.gross_cents == 0
    assert res.validated_minutes_applied == 95


def test_daily_max_cap():
    site, plan = _make_site_and_plan()
    # 14 hours on Wednesday -> 4h free + 10h billable -> 3+4+8*5 = €47 capped to €25.00
    res = calculate_tariff(
        entry_at=datetime(2026, 11, 18, 7, 0, tzinfo=UTC),
        exit_at=datetime(2026, 11, 18, 21, 0, tzinfo=UTC),
        site=site,
        plan=plan,
    )
    assert res.gross_cents == 2500


def test_german_vat_split():
    net, vat = split_german_vat(1190, 1900)
    assert net == 1000
    assert vat == 190
