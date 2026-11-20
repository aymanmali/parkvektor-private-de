import re
from dataclasses import dataclass

GERMAN_KNOWN_DISTRICTS: frozenset[str] = frozenset(
    {
        "A", "AA", "AB", "AC", "AH", "AIC", "AK", "AM", "AN", "AÖ", "AP", "AS", "AUR", "AW", "AZ",
        "B", "BA", "BAD", "BAR", "BB", "BC", "BGL", "BI", "BIR", "BIT", "BK", "BL", "BLK", "BM", "BN",
        "BO", "BOR", "BOT", "BRA", "BRB", "BS", "BT", "BÜS", "BZ", "C", "CB", "CE", "CHA", "CLP", "CO",
        "COC", "COE", "CUX", "CW", "D", "DA", "DAH", "DAN", "DAU", "DBR", "DD", "DE", "DEG", "DEL",
        "DGF", "DH", "DLG", "DN", "DO", "DON", "DU", "DÜW", "E", "EA", "EBE", "ED", "EE", "EF", "EI",
        "EIC", "EL", "EM", "EMD", "EMS", "EN", "ER", "ERB", "ERH", "ERZ", "ES", "ESW", "EU", "F", "FB",
        "FD", "FDS", "FF", "FFB", "FG", "FL", "FN", "FO", "FR", "FRG", "FRI", "FS", "FT", "FÜ", "G",
        "GAP", "GE", "GER", "GF", "GG", "GI", "GL", "GM", "GÖ", "GP", "GR", "GRZ", "GS", "GT", "GTH",
        "GZ", "H", "HA", "HAL", "HAM", "HAS", "HB", "HBN", "HD", "HDH", "HE", "HEF", "HEI", "HER",
        "HF", "HG", "HGW", "HH", "HI", "HL", "HM", "HN", "HO", "HOL", "HOM", "HP", "HR", "HRO", "HS",
        "HSK", "HST", "HU", "HVL", "HWI", "HX", "IGB", "IK", "IN", "IZ", "J", "JL", "K", "KA", "KB",
        "KC", "KE", "KEH", "KF", "KG", "KH", "KI", "KIB", "KL", "KLE", "KN", "KO", "KR", "KS", "KT",
        "KU", "KÜN", "KUS", "KYF", "L", "LA", "LAU", "LB", "LD", "LDK", "LDS", "LER", "LEV", "LG",
        "LI", "LIF", "LIP", "LL", "LM", "LÖ", "LOS", "LRO", "LU", "LÜN", "LUP", "LWL", "M", "MA", "MB",
        "MD", "ME", "MEI", "MG", "MH", "MI", "MIL", "MK", "MKK", "MM", "MN", "MOL", "MOS", "MR", "MS",
        "MSP", "MST", "MTK", "MÜ", "MYK", "MZ", "N", "NB", "ND", "NDH", "NE", "NEA", "NES", "NEW",
        "NF", "NI", "NK", "NM", "NMS", "NOH", "NOM", "NR", "NU", "NVP", "NW", "NWM", "OA", "OAL", "OB",
        "OD", "OE", "OF", "OG", "OH", "OHA", "OHV", "OHZ", "OL", "OPR", "OS", "OSL", "P", "PA", "PAF",
        "PAN", "PB", "PE", "PF", "PI", "PIR", "PLÖ", "PM", "PR", "PS", "R", "RA", "RD", "RE", "REG",
        "RG", "RH", "RO", "ROS", "ROW", "RP", "RS", "RT", "RÜD", "RÜG", "RV", "RW", "RZ", "S", "SAD",
        "SAW", "SB", "SC", "SDL", "SE", "SFA", "SG", "SHG", "SHK", "SHL", "SI", "SIG", "SIM", "SK",
        "SL", "SLF", "SLK", "SLS", "SM", "SN", "SO", "SÖM", "SON", "SP", "SPN", "SR", "ST", "STA",
        "STD", "SU", "SÜW", "SW", "SZ", "TBB", "TDO", "TF", "TIR", "TO", "TÖL", "TR", "TS", "TÜ",
        "TUT", "UE", "UL", "UM", "UN", "V", "VB", "VEC", "VER", "VG", "VIE", "VK", "VR", "VS", "W",
        "WAF", "WAK", "WB", "WE", "WEN", "WES", "WF", "WHV", "WI", "WIL", "WL", "WM", "WN", "WND",
        "WO", "WOB", "WST", "WT", "WTM", "WÜ", "WUG", "WUN", "WW", "WZ", "Z", "ZW",
    }
)

_DE_SEASONAL = re.compile(r"(0[1-9]|1[0-2])/(0[1-9]|1[0-2])$")
_DE_SEPARATED = re.compile(r"^([A-ZÄÖÜ]{1,3})[\s\-]+([A-Z]{1,2})[\s\-]*([1-9][0-9]{0,3})([EH])?$")
_DE_COMPACT = re.compile(r"^([A-ZÄÖÜ]{2,5})([1-9][0-9]{0,3})([EH])?$")


@dataclass(frozen=True)
class EdgePlate:
    raw: str
    normalized: str
    display: str
    is_valid_format: bool


def _split_compact_german_letters(letter_block: str) -> tuple[str, str]:
    """Resolve unseparated OCR letter blocks (e.g. 'MPV' -> ('M', 'PV'), 'GÖAB' -> ('GÖ', 'AB'))."""
    # Prefer longest valid German Unterscheidungszeichen leaving 1-2 middle letters
    for dist_len in (3, 2, 1):
        rem_len = len(letter_block) - dist_len
        if 1 <= rem_len <= 2:
            dist = letter_block[:dist_len]
            mid = letter_block[dist_len:]
            if dist in GERMAN_KNOWN_DISTRICTS and all(ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for ch in mid):
                return dist, mid
    # Fallback split
    mid_len = 2 if len(letter_block) >= 3 else 1
    return letter_block[:-mid_len], letter_block[-mid_len:]


def normalize_edge_plate(raw: str) -> EdgePlate:
    """Self-contained edge German FE-Schrift / EU plate normalizer with Unterscheidungszeichen awareness."""
    work = re.sub(r"\s+", " ", raw.strip().upper())
    work = work.replace("A\u0308", "Ä").replace("O\u0308", "Ö").replace("U\u0308", "Ü")
    season_suffix = ""
    sm = _DE_SEASONAL.search(work)
    if sm:
        season_suffix = f" {sm.group(1)}/{sm.group(2)}"
        work = work[: sm.start()].strip(" -")

    m_sep = _DE_SEPARATED.match(work)
    if m_sep:
        dist, letters, digits, suffix = m_sep.groups()
        suffix = suffix or ""
        return EdgePlate(
            raw=raw,
            normalized=f"{dist}{letters}{digits}{suffix}",
            display=f"{dist}-{letters} {digits}{suffix}{season_suffix}",
            is_valid_format=True,
        )

    compact = re.sub(r"[^A-Z0-9ÄÖÜ]", "", work)
    m_cmp = _DE_COMPACT.match(compact)
    if m_cmp:
        letter_block, digits, suffix = m_cmp.groups()
        suffix = suffix or ""
        dist, letters = _split_compact_german_letters(letter_block)
        return EdgePlate(
            raw=raw,
            normalized=f"{dist}{letters}{digits}{suffix}",
            display=f"{dist}-{letters} {digits}{suffix}{season_suffix}",
            is_valid_format=True,
        )

    return EdgePlate(
        raw=raw,
        normalized=compact,
        display=work,
        is_valid_format=len(compact) >= 4,
    )
