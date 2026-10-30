"""
Module 2 (WTR) - pure calculation rules, kept free of database code so they can be tested in isolation.

Money is always Decimal rounded half-up to two places (SRS 2.5). No rate is hard-coded here: every
number comes from the versioned settings or tariff tables passed in by the caller (SRS 2.5, WB-NF-50).
"""
import calendar
import datetime
import hashlib
import hmac
import math
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")

DUES_BUCKETS = ("PENALTY", "FEE", "ARREAR", "CURRENT")
ALL_BUCKETS = DUES_BUCKETS + ("ADVANCE", "DEPOSIT")

_DOC_SECRET = os.getenv("WATER_DOCUMENT_SECRET", os.getenv("JWT_SECRET_KEY", "urban-water-document-secret"))
_AADHAAR_SALT = os.getenv("WATER_AADHAAR_SALT", "urban-water-aadhaar-salt")


def money(value) -> Decimal:
    """Round to rupees and paise, half-up."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    if value is None:
        return Decimal("0.000")
    return Decimal(str(value)).quantize(THREE_PLACES, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------------------------------------
# Billing cycles
# ----------------------------------------------------------------------------------------------

def cycle_for_date(d: datetime.date, cycle_months: int) -> str:
    """Cycle id 'YYYY-MM' = first month of the cycle containing d. Cycles align to January."""
    if cycle_months < 1 or 12 % cycle_months != 0:
        raise ValueError("Billing cycle length must divide 12 months (1, 2, 3, 4, 6 or 12).")
    start_month = ((d.month - 1) // cycle_months) * cycle_months + 1
    return f"{d.year:04d}-{start_month:02d}"


def parse_cycle(cycle: str) -> Tuple[int, int]:
    try:
        year_s, month_s = cycle.split("-")
        year, month = int(year_s), int(month_s)
    except Exception as exc:
        raise ValueError(f"Cycle '{cycle}' must look like YYYY-MM.") from exc
    if not 1 <= month <= 12:
        raise ValueError(f"Cycle '{cycle}' has an invalid month.")
    return year, month


def cycle_period(cycle: str, cycle_months: int) -> Tuple[datetime.date, datetime.date]:
    year, month = parse_cycle(cycle)
    if cycle_for_date(datetime.date(year, month, 1), cycle_months) != cycle:
        raise ValueError(f"Cycle '{cycle}' does not start a {cycle_months}-month billing cycle.")
    end_index = year * 12 + (month - 1) + cycle_months - 1
    end_year, end_month = divmod(end_index, 12)
    end_month += 1
    last_day = calendar.monthrange(end_year, end_month)[1]
    return datetime.date(year, month, 1), datetime.date(end_year, end_month, last_day)


def previous_cycle(cycle: str, cycle_months: int) -> str:
    year, month = parse_cycle(cycle)
    index = year * 12 + (month - 1) - cycle_months
    y, m = divmod(index, 12)
    return f"{y:04d}-{m + 1:02d}"


def financial_year_start(d: datetime.date) -> datetime.date:
    """Financial year runs April to March (SRS 2.5)."""
    return datetime.date(d.year if d.month >= 4 else d.year - 1, 4, 1)


# ----------------------------------------------------------------------------------------------
# Tariff
# ----------------------------------------------------------------------------------------------

def compute_slab_charges(consumption_kl: Decimal, slabs: Sequence[Dict], free_allowance_kl: Decimal) -> Tuple[Decimal, List[Dict]]:
    """
    Telescopic slab charge. Free allowance (WB-22) is taken off the first kilolitres before slabs apply.
    slabs: [{"uptoKl": 15, "ratePerKl": 7}, {"uptoKl": 30, "ratePerKl": 11}, {"uptoKl": None, "ratePerKl": 20}]
    Returns (total, breakup) where breakup rows are shown on the bill (WB-24).
    """
    consumption = qty(max(Decimal("0"), Decimal(str(consumption_kl))))
    free = qty(max(Decimal("0"), Decimal(str(free_allowance_kl or 0))))
    breakup: List[Dict] = []
    total = Decimal("0.00")

    free_used = min(consumption, free)
    if free_used > 0:
        breakup.append({"fromKl": 0.0, "toKl": float(free_used), "units": float(free_used), "rate": 0.0, "amount": 0.0, "label": "FREE_ALLOWANCE"})

    lower = Decimal("0")
    for slab in slabs:
        upto = slab.get("uptoKl")
        rate = Decimal(str(slab.get("ratePerKl", 0)))
        upper = Decimal(str(upto)) if upto is not None else None
        # units of consumption that fall inside (lower, upper], after removing the free allowance
        band_low = max(lower, free_used)
        band_high = consumption if upper is None else min(consumption, upper)
        units = band_high - band_low
        if units > 0:
            amount = money(units * rate)
            total += amount
            breakup.append({
                "fromKl": float(lower),
                "toKl": float(upper) if upper is not None else None,
                "units": float(qty(units)),
                "rate": float(rate),
                "amount": float(amount),
                "label": "SLAB",
            })
        if upper is None or consumption <= upper:
            break
        lower = upper
    return money(total), breakup


def validate_slabs(slabs: Sequence[Dict]) -> None:
    if not slabs:
        raise ValueError("A tariff needs at least one slab.")
    previous = Decimal("0")
    for index, slab in enumerate(slabs):
        rate = slab.get("ratePerKl")
        if rate is None or Decimal(str(rate)) < 0:
            raise ValueError(f"Slab {index + 1}: rate per kilolitre must be zero or more.")
        upto = slab.get("uptoKl")
        if upto is None:
            if index != len(slabs) - 1:
                raise ValueError("Only the last slab may be open-ended (no upper limit).")
        else:
            upper = Decimal(str(upto))
            if upper <= previous:
                raise ValueError(f"Slab {index + 1}: upper limit must be greater than {previous} kL.")
            previous = upper
    if slabs[-1].get("uptoKl") is not None:
        raise ValueError("The last slab must be open-ended so every kilolitre is charged.")


def compute_bill_amounts(
    *,
    basis: str,
    consumption_kl: Decimal,
    pipe_size_mm: int,
    slabs: Sequence[Dict],
    flat_rates: Dict[str, float],
    minimum_charge,
    fixed_charge,
    cess_percent,
    free_allowance_kl,
    cycle_months: int,
) -> Dict:
    """
    Works out the charges for one bill.
    - Metered (ACTUAL / AVERAGE): slab charge, but never below the minimum charge (WB-20).
    - Non-metered (FLAT): flat rate for category and pipe size, per month, times cycle months (WB-17).
    Fixed charge and minimum charge are monthly amounts and scale with the cycle length.
    Cess is a percentage of the water charge.
    """
    months = Decimal(cycle_months)
    if basis == "FLAT":
        rate = flat_rates.get(str(pipe_size_mm))
        if rate is None:
            raise ValueError(f"No flat rate set for pipe size {pipe_size_mm} mm in this tariff.")
        water_charge = money(Decimal(str(rate)) * months)
        breakup = [{"label": "FLAT_RATE", "pipeSizeMm": pipe_size_mm, "monthlyRate": float(money(rate)), "months": cycle_months, "amount": float(water_charge)}]
    else:
        slab_total, breakup = compute_slab_charges(consumption_kl, slabs, Decimal(str(free_allowance_kl or 0)))
        minimum = money(Decimal(str(minimum_charge or 0)) * months)
        water_charge = slab_total
        if slab_total < minimum:
            breakup.append({"label": "MINIMUM_CHARGE_TOP_UP", "amount": float(money(minimum - slab_total))})
            water_charge = minimum
    fixed = money(Decimal(str(fixed_charge or 0)) * months)
    cess = money(water_charge * Decimal(str(cess_percent or 0)) / Decimal("100"))
    return {
        "waterCharge": water_charge,
        "fixedCharge": fixed,
        "cess": cess,
        "currentDemand": money(water_charge + fixed + cess),
        "breakup": breakup,
    }


def average_consumption(history: Iterable, method: Dict) -> Optional[Decimal]:
    """
    Average billing (WB-16). history: consumptions of earlier ACTUAL bills, newest first.
    method: {"type": "LAST_N_ACTUAL", "n": 3}. Returns None when there is no history.
    """
    if (method or {}).get("type", "LAST_N_ACTUAL") != "LAST_N_ACTUAL":
        raise ValueError(f"Unsupported average billing method: {method.get('type')}")
    n = int((method or {}).get("n", 3))
    values = [Decimal(str(v)) for v in list(history)[:n]]
    if not values:
        return None
    return qty(sum(values) / Decimal(len(values)))


def classify_reading(
    *,
    reading_value: Decimal,
    previous_value: Decimal,
    history: Sequence,
    rules: Dict,
) -> Tuple[str, Decimal]:
    """
    Reading checks before billing (WB-15).
    Returns (flag, consumption). Flags: LOWER_THAN_LAST, HIGH, LOW, NONE.
    rules: {"highPercent": 100, "lowPercent": 50, "minHistory": 1, "n": 3}
    """
    consumption = qty(Decimal(str(reading_value)) - Decimal(str(previous_value)))
    if consumption < 0:
        return "LOWER_THAN_LAST", consumption
    min_history = int(rules.get("minHistory", 1))
    usable = [Decimal(str(v)) for v in list(history)[: int(rules.get("n", 3))]]
    if len(usable) < min_history or not usable:
        return "NONE", consumption
    avg = sum(usable) / Decimal(len(usable))
    if avg <= 0:
        # usual consumption is zero; any positive jump above the high limit floor is flagged
        return ("HIGH" if consumption > Decimal(str(rules.get("zeroBaseHighKl", 10))) else "NONE"), consumption
    high_limit = avg * (Decimal("1") + Decimal(str(rules.get("highPercent", 100))) / Decimal("100"))
    low_limit = avg * (Decimal("1") - Decimal(str(rules.get("lowPercent", 50))) / Decimal("100"))
    if consumption > high_limit:
        return "HIGH", consumption
    if consumption < low_limit:
        return "LOW", consumption
    return "NONE", consumption


# ----------------------------------------------------------------------------------------------
# Payments and dues
# ----------------------------------------------------------------------------------------------

def allocate_payment(amount: Decimal, balances: Dict[str, Decimal], order: Sequence[str]) -> Dict[str, Decimal]:
    """
    Splits a payment across dues buckets in the configured order (WB-32). Whatever is left over is held
    as ADVANCE credit. Returns {bucket: amount_applied} with every value positive.
    """
    remaining = money(amount)
    if remaining <= 0:
        raise ValueError("Payment amount must be more than zero.")
    unknown = [b for b in order if b not in DUES_BUCKETS]
    if unknown or sorted(order) != sorted(DUES_BUCKETS):
        raise ValueError(f"Payment allocation order must list each of {', '.join(DUES_BUCKETS)} exactly once.")
    applied: Dict[str, Decimal] = {}
    for bucket in order:
        due = money(balances.get(bucket, 0))
        if due <= 0 or remaining <= 0:
            continue
        take = min(due, remaining)
        applied[bucket] = take
        remaining = money(remaining - take)
    if remaining > 0:
        applied["ADVANCE"] = remaining
    return applied


def age_outstanding(principal_due: Decimal, bills: Sequence[Dict], opening_arrear_date: Optional[datetime.date], as_of: datetime.date) -> List[Dict]:
    """
    Splits outstanding principal (arrear + current) over bills, newest first, because payments clear older
    dues first (WB-32 default order). bills: [{"id","billNo","dueDate","currentDemand"}] newest first.
    Returns [{"billId","billNo","dueDate","unpaid","ageDays"}]; any principal older than every bill is
    reported against the opening (migrated) arrear, aged from the date it was taken on.
    """
    remaining = money(principal_due)
    rows: List[Dict] = []
    for bill in bills:
        if remaining <= 0:
            break
        part = min(money(bill["currentDemand"]), remaining)
        if part > 0:
            rows.append({
                "billId": bill["id"],
                "billNo": bill["billNo"],
                "dueDate": bill["dueDate"],
                "unpaid": part,
                "ageDays": max(0, (as_of - bill["dueDate"]).days),
            })
            remaining = money(remaining - part)
    if remaining > 0:
        if opening_arrear_date is not None:
            age = max(0, (as_of - opening_arrear_date).days)
        else:
            age = max((r["ageDays"] for r in rows), default=0)
        rows.append({
            "billId": None,
            "billNo": "OPENING-ARREAR",
            "dueDate": opening_arrear_date,
            "unpaid": remaining,
            "ageDays": age,
        })
    return rows


AGE_BANDS = (("0-30", 0, 30), ("31-90", 31, 90), ("91-180", 91, 180), ("181-365", 181, 365), ("365+", 366, None))


def age_band(age_days: int) -> str:
    for label, low, high in AGE_BANDS:
        if age_days >= low and (high is None or age_days <= high):
            return label
    return "365+"


def payment_status(dues: Dict[str, Decimal]) -> str:
    """PAID when nothing is owed, DUE when only the current bill is open, ARREARS when older dues remain."""
    arrear_like = money(dues.get("ARREAR", 0)) + money(dues.get("PENALTY", 0)) + money(dues.get("FEE", 0))
    if arrear_like > 0:
        return "ARREARS"
    if money(dues.get("CURRENT", 0)) > 0:
        return "DUE"
    return "PAID"


# ----------------------------------------------------------------------------------------------
# Misc
# ----------------------------------------------------------------------------------------------

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalise_address(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return " ".join(cleaned.split())


def document_code(doc_type: str, number: str, amount) -> str:
    """Short code printed in the QR so anyone can check a bill/receipt is genuine (SRS 3.1.1)."""
    msg = f"{doc_type}|{number}|{money(amount)}".encode("utf-8")
    return hmac.new(_DOC_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:12].upper()


def hash_aadhaar(aadhaar: str) -> Tuple[str, str]:
    """Returns (salted hash, last 4 digits). The full number is never stored (WB-NF-21)."""
    digits = "".join(ch for ch in (aadhaar or "") if ch.isdigit())
    if len(digits) != 12:
        raise ValueError("Aadhaar number must have 12 digits.")
    digest = hashlib.sha256((_AADHAAR_SALT + digits).encode("utf-8")).hexdigest()
    return digest, digits[-4:]


def mask_mobile(mobile: Optional[str]) -> Optional[str]:
    if not mobile:
        return mobile
    return ("*" * max(0, len(mobile) - 4)) + mobile[-4:]
