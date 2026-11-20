import re
from dataclasses import dataclass

# Curated core set of German Unterscheidungszeichen (major cities, districts & umlaut districts).
# Valid 1-3 letter German prefixes outside this set are still accepted structurally if they match
# official StVZO FE-Schrift syntax, while known codes boost DE country classification over neighbors.
GERMAN_KNOWN_DISTRICTS: frozenset[str] = frozenset(
    {
        "A", "AA", "AB", "AC", "AE", "AH", "AIC", "AK", "AM", "AN", "AÖ", "AP", "AS", "AUR", "AW", "AZ",
        "B", "BA", "BAD", "BAR", "BB", "BC", "BGL", "BI", "BIR", "BIT", "BK", "BL", "BLK", "BM", "BN",
        "BO", "BOR", "BOT", "BRA", "BRB", "BS", "BT", "BÜS", "BZ",
        "C", "CB", "CE", "CHA", "CLP", "CO", "COC", "COE", "CUX", "CW",
        "D", "DA", "DAH", "DAN", "DAU", "DBR", "DD", "DE", "DEG", "DEL", "DGF", "DH", "DLG", "DN", "DO",
        "DON", "DU", "DÜW",
        "E", "EA", "EBE", "ED", "EE", "EF", "EI", "EIC", "EL", "EM", "EMD", "EMS", "EN", "ER", "ERB",
        "ERH", "ERZ", "ES", "ESW", "EU",
        "F", "FB", "FD", "FDS", "FF", "FFB", "FG", "FL", "FN", "FO", "FR", "FRG", "FRI", "FS", "FT", "FÜ",
        "G", "GAP", "GE", "GER", "GF", "GG", "GI", "GL", "GM", "GÖ", "GP", "GR", "GRZ", "GS", "GT", "GTH", "GZ",
        "H", "HA", "HAL", "HAM", "HAS", "HB", "HBN", "HD", "HDH", "HE", "HEF", "HEI", "HER", "HF", "HG",
        "HGW", "HH", "HI", "HL", "HM", "HN", "HO", "HOL", "HOM", "HP", "HR", "HRO", "HS", "HSK", "HST",
        "HU", "HVL", "HWI", "HX",
        "IGB", "IK", "IN", "IZ",
        "J", "JL",
        "K", "KA", "KB", "KC", "KE", "KEH", "KF", "KG", "KH", "KI", "KIB", "KL", "KLE", "KN", "KO", "KR",
        "KS", "KT", "KU", "KÜN", "KUS", "KYF",
        "L", "LA", "LAU", "LB", "LD", "LDK", "LDS", "LER", "LEV", "LG", "LI", "LIF", "LIP", "LL", "LM",
        "LÖ", "LOS", "LRO", "LU", "LÜN", "LUP", "LWL",
        "M", "MA", "MB", "MD", "ME", "MEI", "MG", "MH", "MI", "MIL", "MK", "MKK", "MM", "MN", "MOL", "MOS",
        "MR", "MS", "MSP", "MST", "MTK", "MÜ", "MYK", "MZ",
        "N", "NB", "ND", "NDH", "NE", "NEA", "NES", "NEW", "NF", "NI", "NK", "NM", "NMS", "NOH", "NOM", "NR",
        "NU", "NVP", "NW", "NWM",
        "OA", "OAL", "OB", "OD", "OE", "OF", "OG", "OH", "OHA", "OHV", "OHZ", "OL", "OPR", "OS", "OSL",
        "P", "PA", "PAF", "PAN", "PB", "PE", "PF", "PI", "PIR", "PLÖ", "PM", "PR", "PS",
        "R", "RA", "RD", "RE", "REG", "RG", "RH", "RO", "ROS", "ROW", "RP", "RS", "RT", "RÜD", "RÜG", "RV", "RW", "RZ",
        "S", "SAD", "SAW", "SB", "SC", "SDL", "SE", "SFA", "SG", "SHG", "SHK", "SHL", "SI", "SIG", "SIM",
        "SK", "SL", "SLF", "SLK", "SLS", "SM", "SN", "SO", "SÖM", "SON", "SP", "SPN", "SR", "ST", "STA",
        "STD", "SU", "SÜW", "SW", "SZ",
        "TBB", "TDO", "TF", "TIR", "TO", "TÖL", "TR", "TS", "TÜ", "TUT",
        "UE", "UL", "UM", "UN",
        "V", "VB", "VEC", "VER", "VG", "VIE", "VK", "VR", "VS",
        "W", "WAF", "WAK", "WB", "WE", "WEN", "WES", "WF", "WHV", "WI", "WIL", "WL", "WM", "WN", "WND",
        "WO", "WOB", "WST", "WT", "WTM", "WÜ", "WUG", "WUN", "WW", "WZ",
        "Z", "ZW",
    }
)

# German plate patterns (after cleaning whitespace/separators)
_DE_SEASONAL_TAIL = re.compile(r"(0[1-9]|1[0-2])/(0[1-9]|1[0-2])$")
_DE_STANDARD_REGEX = re.compile(
    r"^([A-ZÄÖÜ]{1,3})[\s\-]*([A-Z]{1,2})[\s\-]*([1-9][0-9]{0,3})([EH])?$"
)
_DE_DEALER_SHORT_REGEX = re.compile(r"^([A-ZÄÖÜ]{1,3})[\s\-]*(0[467][0-9]{3,4})$")
_DE_DIPLOMATIC_REGEX = re.compile(r"^0[\s\-]*([0-9]{1,3})[\s\-]*([0-9]{1,3})$")

# Neighboring EU/EEA common plate regexes
_EU_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NL", re.compile(r"^([A-Z]{2}[0-9]{2}[A-Z]{2}|[0-9]{2}[A-Z]{2}[0-9]{2}|[A-Z]{2}[0-9]{3}[A-Z]|[A-Z][0-9]{3}[A-Z]{2}|[0-9]{2}[A-Z]{3}[0-9]|[0-9][A-Z]{3}[0-9]{2})$")),
    ("FR", re.compile(r"^[A-Z]{2}[0-9]{3}[A-Z]{2}$")),
    ("IT", re.compile(r"^[A-Z]{2}[0-9]{3}[A-Z]{2}$")),
    ("CH", re.compile(r"^(AG|AI|AR|BE|BL|BS|FR|GE|GL|GR|JU|LU|NE|NW|OW|SG|SH|SO|SZ|TG|TI|UR|VD|VS|ZG|ZH)[0-9]{1,6}$")),
    ("AT", re.compile(r"^(W|G|L|S|I|K|P|E|B|BL|BN|BR|BZ|DL|DO|EF|EU|FB|FE|FK|FR|GF|GM|GR|GS|GU|HA|HE|HF|HL|HO|IL|IM|JE|JO|KB|KI|KL|KO|KR|KS|KU|LA|LB|LE|LF|LI|LL|LN|LZ|MA|MD|ME|MI|MT|MU|ND|NK|OP|OW|PE|PL|RE|RI|RO|SB|SD|SE|SL|SO|SP|SR|ST|SV|SW|SZ|TA|TU|UU|VB|VI|VK|VL|VO|WB|WE|WL|WN|WO|WT|WU|WY|WZ|ZE|ZT|ZW)[0-9]{2,5}[A-Z]{1,3}$")),
    ("PL", re.compile(r"^[A-Z]{2,3}[A-Z0-9]{4,5}$")),
    ("CZ", re.compile(r"^[0-9][A-Z][0-9][0-9]{4}$")),
    ("BE", re.compile(r"^[1-9][A-Z]{3}[0-9]{3}$")),
    ("DK", re.compile(r"^[A-Z]{2}[0-9]{5}$")),
]

# OCR confusion pairs with lower edit cost (0.35 instead of 1.0)
_OCR_CONFUSIONS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"O", "0"}),
        frozenset({"Q", "0"}),
        frozenset({"D", "0"}),
        frozenset({"I", "1"}),
        frozenset({"L", "1"}),
        frozenset({"B", "8"}),
        frozenset({"S", "5"}),
        frozenset({"Z", "2"}),
        frozenset({"G", "6"}),
        frozenset({"A", "4"}),
    }
)


@dataclass(frozen=True)
class ParsedPlate:
    raw: str
    normalized: str
    display: str
    country: str
    plate_type: str  # STANDARD | EV | HISTORIC | SEASONAL | DEALER | DIPLOMATIC | EU_FOREIGN | UNKNOWN
    valid: bool
    season_start_month: int | None = None
    season_end_month: int | None = None


def parse_plate(raw: str) -> ParsedPlate:
    """Parse and normalize German FE-Schrift and neighboring EU license plates."""
    cleaned = raw.strip().upper()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Normalize unicode umlaut combinations and common German plate separators (en-dash, middle dot)
    cleaned = cleaned.replace("A\u0308", "Ä").replace("O\u0308", "Ö").replace("U\u0308", "Ü")
    cleaned = re.sub(r"[–—−·•.]", "-", cleaned)

    season_start: int | None = None
    season_end: int | None = None
    work = cleaned

    # Check for seasonal suffix like "04/10" at the end
    season_match = _DE_SEASONAL_TAIL.search(work)
    if season_match:
        season_start = int(season_match.group(1))
        season_end = int(season_match.group(2))
        work = work[: season_match.start()].strip(" -")

    # 1. German Diplomatic (e.g. "0-17-1")
    dip_match = _DE_DIPLOMATIC_REGEX.match(work)
    if dip_match:
        norm = f"0{dip_match.group(1)}{dip_match.group(2)}"
        disp = f"0-{dip_match.group(1)}-{dip_match.group(2)}"
        return ParsedPlate(raw=raw, normalized=norm, display=disp, country="DE", plate_type="DIPLOMATIC", valid=True)

    # 2. German Dealer / Short-Term Red/Yellow Plates (e.g. "M-06123")
    dealer_match = _DE_DEALER_SHORT_REGEX.match(work)
    if dealer_match and dealer_match.group(1) in GERMAN_KNOWN_DISTRICTS:
        dist, num = dealer_match.group(1), dealer_match.group(2)
        return ParsedPlate(
            raw=raw,
            normalized=f"{dist}{num}",
            display=f"{dist}-{num}",
            country="DE",
            plate_type="DEALER",
            valid=True,
        )

    # 3. German Standard / EV / Historic / Seasonal FE-Schrift
    # Prefer spaced/hyphenated capture first; if completely compact, attempt smart German split
    de_match = _DE_STANDARD_REGEX.match(work)
    if de_match:
        dist, letters, digits, suffix = de_match.groups()
        # Only treat as German if separator was present OR district is in known German list
        has_separator = ("-" in work) or (" " in work)
        # Disambiguate compact plates (like FR "AB123CD" or CH "ZH12345") before assuming DE
        compact = re.sub(r"[^A-Z0-9ÄÖÜ]", "", work)
        if has_separator or dist in GERMAN_KNOWN_DISTRICTS:
            # Guard against 2-letter Swiss/Austrian/French formats without hyphen
            if not has_separator and _matches_non_de_explicit(compact):
                pass
            else:
                suffix = suffix or ""
                if season_start is not None:
                    p_type = "SEASONAL"
                    disp = f"{dist}-{letters} {digits}{suffix} {season_start:02d}/{season_end:02d}"
                    norm = f"{dist}{letters}{digits}{suffix}"
                elif suffix == "E":
                    p_type = "EV"
                    disp = f"{dist}-{letters} {digits}E"
                    norm = f"{dist}{letters}{digits}E"
                elif suffix == "H":
                    p_type = "HISTORIC"
                    disp = f"{dist}-{letters} {digits}H"
                    norm = f"{dist}{letters}{digits}H"
                else:
                    p_type = "STANDARD"
                    disp = f"{dist}-{letters} {digits}"
                    norm = f"{dist}{letters}{digits}"
                return ParsedPlate(
                    raw=raw,
                    normalized=norm,
                    display=disp,
                    country="DE",
                    plate_type=p_type,
                    valid=True,
                    season_start_month=season_start,
                    season_end_month=season_end,
                )

    # 4. Neighboring EU/EEA plates
    compact = re.sub(r"[^A-Z0-9ÄÖÜ]", "", work)
    for country_code, pattern in _EU_PATTERNS:
        if pattern.match(compact):
            return ParsedPlate(
                raw=raw,
                normalized=compact,
                display=cleaned,
                country=country_code,
                plate_type="EU_FOREIGN",
                valid=True,
            )

    # 5. Fallback for compact DE plate with unknown 1-3 letter district
    if de_match:
        dist, letters, digits, suffix = de_match.groups()
        suffix = suffix or ""
        return ParsedPlate(
            raw=raw,
            normalized=f"{dist}{letters}{digits}{suffix}",
            display=f"{dist}-{letters} {digits}{suffix}",
            country="DE",
            plate_type="EV" if suffix == "E" else ("HISTORIC" if suffix == "H" else "STANDARD"),
            valid=True,
        )

    return ParsedPlate(
        raw=raw,
        normalized=compact,
        display=cleaned,
        country="EU",
        plate_type="UNKNOWN",
        valid=len(compact) >= 4,
    )


def _matches_non_de_explicit(compact: str) -> bool:
    for code, pattern in _EU_PATTERNS:
        if code in {"FR", "IT", "NL", "CH", "AT", "BE", "CZ"} and pattern.match(compact):
            return True
    return False


def ocr_weighted_distance(a: str, b: str) -> float:
    """Weighted Levenshtein distance favoring common ANPR OCR confusions (O/0, B/8, I/1, S/5)."""
    if a == b:
        return 0.0
    m, n = len(a), len(b)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = float(i)
    for j in range(n + 1):
        dp[0][j] = float(j)

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                cost = 0.0
            elif frozenset({a[i - 1], b[j - 1]}) in _OCR_CONFUSIONS:
                cost = 0.35
            else:
                cost = 1.0
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,      # deletion
                dp[i][j - 1] + 1.0,      # insertion
                dp[i - 1][j - 1] + cost, # substitution
            )
    return dp[m][n]


def mask_plate_for_public(plate_display: str) -> str:
    """Partially mask plate in unauthenticated responses where desired while staying recognizable."""
    if len(plate_display) <= 4:
        return plate_display
    return f"{plate_display[:3]}•••{plate_display[-2:]}"
