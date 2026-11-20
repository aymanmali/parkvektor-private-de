from app.domain.plates_de import ocr_weighted_distance, parse_plate


def test_standard_german_plate_with_umlaut():
    # Official German FZV plates allow umlauts (Ä, Ö, Ü) in Unterscheidungszeichen (e.g. GÖ, MÜ, FÜ, WÜ)
    p = parse_plate("  gö-ab 901 ")
    assert p.valid is True
    assert p.country == "DE"
    assert p.plate_type == "STANDARD"
    assert p.normalized == "GÖAB901"
    assert p.display == "GÖ-AB 901"

    p2 = parse_plate("mü-kl 42E")
    assert p2.country == "DE"
    assert p2.plate_type == "EV"
    assert p2.normalized == "MÜKL42E"


def test_german_ev_and_historic_plates():
    ev = parse_plate("M-PV 2026E")
    assert ev.country == "DE"
    assert ev.plate_type == "EV"
    assert ev.normalized == "MPV2026E"
    assert ev.display == "M-PV 2026E"

    hist = parse_plate("HH AB 12H")
    assert hist.country == "DE"
    assert hist.plate_type == "HISTORIC"
    assert hist.normalized == "HHAB12H"
    assert hist.display == "HH-AB 12H"

    unicode_sep = parse_plate("M–PV 2026E")
    assert unicode_sep.valid is True
    assert unicode_sep.normalized == "MPV2026E"
    assert unicode_sep.display == "M-PV 2026E"

    dot_sep = parse_plate("M·AB 1234")
    assert dot_sep.valid is True
    assert dot_sep.normalized == "MAB1234"
    assert dot_sep.display == "M-AB 1234"


def test_german_seasonal_plate():
    seas = parse_plate("K-AB 911 04/10")
    assert seas.country == "DE"
    assert seas.plate_type == "SEASONAL"
    assert seas.normalized == "KAB911"
    assert seas.season_start_month == 4
    assert seas.season_end_month == 10
    assert seas.display == "K-AB 911 04/10"

    same_month = parse_plate("K-AB 911 04/04")
    assert same_month.season_start_month is None
    assert same_month.plate_type != "SEASONAL"


def test_german_dealer_and_diplomatic_plates():
    dealer = parse_plate("M-06123")
    assert dealer.country == "DE"
    assert dealer.plate_type == "DEALER"

    dip = parse_plate("0-17-1")
    assert dip.country == "DE"
    assert dip.plate_type == "DIPLOMATIC"


def test_neighboring_eu_plates():
    ch = parse_plate("ZH 123456")
    assert ch.country == "CH"
    assert ch.plate_type == "EU_FOREIGN"

    at = parse_plate("W 12345A")
    assert at.country == "AT"
    assert at.plate_type == "EU_FOREIGN"

    fr = parse_plate("AB-123-CD")
    assert fr.country == "FR"
    assert fr.plate_type == "EU_FOREIGN"


def test_ocr_weighted_distance_favors_confusions():
    # O <-> 0 and B <-> 8 cost 0.35 each, well under fuzzy threshold 1.0
    assert ocr_weighted_distance("KDO881", "KD0881") < 0.5
    assert ocr_weighted_distance("MAB1234", "MA81234") < 0.5
    # Completely different plate has high distance
    assert ocr_weighted_distance("MAB1234", "BXY999") > 3.0
