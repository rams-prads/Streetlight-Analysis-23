"""
Module 1 (PTX) - property tax rules engine and pure helpers (no database code).

Money is Decimal rounded half-up to two places (SRS 2.5). No rate is hard-coded: every number comes from the
approved rate table or the versioned settings passed in by the caller (SRS 2.5, PT-10, PT-NF-50).

Tax method (all values from the rate table, placeholders until GWMC confirms - SRS Appendix A #2):
  built property, per floor:  monthly rental value per sq ft (by rate zone, use and construction)
                              x built-up area x 12 x occupancy factor (owner / tenant)
                              less depreciation by age of the building  = annual rental value (ARV)
                              ARV x tax rate for the use                = property tax for the floor
  small homes:                residential ARV up to the exempt limit pays no property tax
  vacant land:                site area (sq yd) x vacant land rate for the rate zone
  then:                       exemption / concession percent (PT-20), minimum tax, cess as % of property tax
"""
import datetime
import hashlib
import hmac
import math
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Tuple

TWO = Decimal("0.01")
DUES_BUCKETS = ("PENALTY", "FEE", "ARREAR", "CURRENT")

_DOC_SECRET = os.getenv("PTX_DOCUMENT_SECRET", os.getenv("JWT_SECRET_KEY", "urban-ptx-document-secret"))
_AADHAAR_SALT = os.getenv("PTX_AADHAAR_SALT", "urban-ptx-aadhaar-salt")


def money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO, rounding=ROUND_HALF_UP)


def dec(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


# ------------------------------------------------------------------------------------------------
# Financial years and demand periods (financial year runs April to March - SRS 2.5)
# ------------------------------------------------------------------------------------------------

def financial_year_of(d: datetime.date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_start_year(fy: str) -> int:
    try:
        return int(fy.split("-")[0])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Financial year '{fy}' must look like 2026-27.") from exc


def financial_year_start(d: datetime.date) -> datetime.date:
    return datetime.date(fy_start_year(financial_year_of(d)), 4, 1)


def period_for_date(d: datetime.date, frequency: str) -> str:
    fy = financial_year_of(d)
    if frequency == "YEARLY":
        return f"{fy}-Y"
    if frequency != "HALF_YEARLY":
        raise ValueError("Demand frequency must be HALF_YEARLY or YEARLY.")
    return f"{fy}-H1" if 4 <= d.month <= 9 else f"{fy}-H2"


def period_bounds(period: str) -> Tuple[datetime.date, datetime.date]:
    """2026-27-H1 -> 01-04-2026..30-09-2026; -H2 -> 01-10-2026..31-03-2027; -Y -> whole year."""
    try:
        fy, part = period.rsplit("-", 1)
        start_year = fy_start_year(fy)
    except ValueError as exc:
        raise ValueError(f"Period '{period}' must look like 2026-27-H1, 2026-27-H2 or 2026-27-Y.") from exc
    if f"{start_year}-{str(start_year + 1)[-2:]}" != fy:
        raise ValueError(f"Period '{period}' has an invalid financial year.")
    if part == "H1":
        return datetime.date(start_year, 4, 1), datetime.date(start_year, 9, 30)
    if part == "H2":
        return datetime.date(start_year, 10, 1), datetime.date(start_year + 1, 3, 31)
    if part == "Y":
        return datetime.date(start_year, 4, 1), datetime.date(start_year + 1, 3, 31)
    raise ValueError(f"Period '{period}' must end in H1, H2 or Y.")


def period_start_for(d: datetime.date, frequency: str) -> datetime.date:
    """Assessments apply from the start of the demand period containing their effective date."""
    return period_bounds(period_for_date(d, frequency))[0]


def periods_between(first: datetime.date, last: datetime.date, frequency: str) -> List[str]:
    """Every period from the one containing `first` up to the one containing `last`."""
    out: List[str] = []
    cursor = period_start_for(first, frequency)
    while cursor <= last:
        p = period_for_date(cursor, frequency)
        out.append(p)
        cursor = period_bounds(p)[1] + datetime.timedelta(days=1)
    return out


def period_label(period: str) -> str:
    fy, part = period.rsplit("-", 1)
    return {"H1": f"First half {fy} (Apr-Sep)", "H2": f"Second half {fy} (Oct-Mar)", "Y": f"Year {fy}"}.get(part, period)


def period_share(amount: Decimal, period: str) -> Decimal:
    """Splits an annual amount so the two halves always add up to the annual figure exactly."""
    amount = money(amount)
    part = period.rsplit("-", 1)[1]
    if part == "Y":
        return amount
    first = money(amount / 2)
    return first if part == "H1" else money(amount - first)


def add_months(d: datetime.date, months: int) -> datetime.date:
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last_day = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return datetime.date(year, month, min(d.day, last_day))


# ------------------------------------------------------------------------------------------------
# Rate table rules
# ------------------------------------------------------------------------------------------------

REQUIRED_RULE_KEYS = ("rateZones", "monthlyRentalValuePerSqft", "occupancyFactor", "depreciation",
                      "taxRatePercentOfArv", "cess", "vacantLandRatePerSqydPerYear")


def validate_rules(rules: Dict) -> None:
    missing = [k for k in REQUIRED_RULE_KEYS if k not in rules]
    if missing:
        raise ValueError("Rate table is missing: " + ", ".join(missing) + ".")
    if "default" not in rules["rateZones"]:
        raise ValueError("rateZones needs a 'default' zone.")
    for zone, by_use in rules["monthlyRentalValuePerSqft"].items():
        for use, by_construction in by_use.items():
            for ctype, rate in by_construction.items():
                if dec(rate) < 0:
                    raise ValueError(f"Rental value for {zone}/{use}/{ctype} cannot be negative.")
    bands = rules["depreciation"]
    if not bands or bands[0].get("fromAge", 0) != 0 or bands[-1].get("toAge") is not None:
        raise ValueError("Depreciation bands must start at age 0 and the last band must be open-ended.")
    for use, pct in rules["taxRatePercentOfArv"].items():
        if not (0 <= dec(pct) <= 100):
            raise ValueError(f"Tax rate for {use} must be between 0 and 100 percent.")
    for c in rules["cess"]:
        if not c.get("code") or dec(c.get("percentOfTax", -1)) < 0:
            raise ValueError("Each cess needs a code and a percent of tax of zero or more.")
    for road, pct in (rules.get("roadClassFactorPercent") or {}).items():
        if dec(pct) <= 0 or dec(pct) > 300:
            raise ValueError(f"Road class factor for {road} must be more than 0 and at most 300 percent.")
    for kind, spec in (rules.get("rooftopInstallations") or {}).items():
        if dec(spec.get("monthlyRatePerSqft", -1)) < 0:
            raise ValueError(f"Rooftop installation {kind} needs a monthly rate per sq ft of zero or more.")
    acc = rules.get("accommodation")
    if acc and acc.get("usageCode") not in rules["taxRatePercentOfArv"]:
        raise ValueError("Accommodation use must be one of the uses that have a tax rate.")
    sb = rules.get("setbackPenalty")
    if sb and not (0 <= dec(sb.get("percentOfTax", -1)) <= 100):
        raise ValueError("Setback penalty must be between 0 and 100 percent of tax.")


def rate_zone(rules: Dict, ward_number: Optional[int], locality_code: Optional[str]) -> str:
    zones = rules["rateZones"]
    if locality_code and locality_code in zones.get("byLocalityCode", {}):
        return zones["byLocalityCode"][locality_code]
    if ward_number is not None and str(ward_number) in zones.get("byWardNumber", {}):
        return zones["byWardNumber"][str(ward_number)]
    return zones["default"]


def _depreciation(rules: Dict, age: int) -> Decimal:
    for band in rules["depreciation"]:
        if age >= int(band.get("fromAge", 0)) and (band.get("toAge") is None or age <= int(band["toAge"])):
            return dec(band.get("percent", 0))
    return Decimal("0")


def compute_annual_tax(*, rules: Dict, property_type: str, site_area_sqyd, construction_year: Optional[int],
                       floors: Sequence[Dict], ward_number: Optional[int], locality_code: Optional[str],
                       as_of: datetime.date, exemption: Optional[Dict] = None, labels: Optional[Dict] = None,
                       road_class: Optional[str] = None, setback: Optional[Dict] = None) -> Dict:
    """
    Works out the annual tax and the calculation sheet shown to officer and owner (PT-10, PT-11, PT-20).
    floors: [{"floorNo", "usageCode", "constructionCode", "builtupSqft", "occupancy", "portion", "rooftopType", "declaredAccommodation"}]
      portion: FULL (default), PART (part of a floor used differently, PT-31), COMMON (share of an apartment's common areas, PT-07)
               or ROOFTOP (tower, hoarding or other installation on the roof, PT-31).
      declaredAccommodation: the owner declares guest / paying-guest / lodging use of this area (PT-33).
    road_class: code of the road the property is on; scales the rental value (PT-32).
    setback: {"approvedFt", "measuredFt"} from the inspection; a shortfall adds a penalty (PT-12).
    exemption: {"code", "percent", "nameEn"} or None. labels: code -> English name for the sheet.
    """
    labels = labels or {}
    zone = rate_zone(rules, ward_number, locality_code)
    road_factor = dec((rules.get("roadClassFactorPercent") or {}).get(road_class, 100)) / Decimal("100") if road_class else Decimal("1")
    lines: List[Dict] = []
    steps: List[str] = []
    tax = Decimal("0.00")
    tax_component = "PROPERTY_TAX"

    if property_type == "VACANT_LAND":
        rate = rules["vacantLandRatePerSqydPerYear"].get(zone)
        if rate is None:
            raise ValueError(f"No vacant land rate is set for rate zone {zone}.")
        area = dec(site_area_sqyd)
        if area <= 0:
            raise ValueError("Site area is needed to assess vacant land.")
        tax = money(area * dec(rate) * road_factor)
        tax_component = "VACANT_LAND_TAX"
        lines.append({"kind": "VACANT_LAND", "siteAreaSqyd": float(area), "ratePerSqydPerYear": float(dec(rate)), "roadFactor": float(road_factor), "tax": float(tax)})
        steps.append(f"Vacant land: {area} sq yd x Rs {dec(rate)} per sq yd per year"
                     + (f" x {road_factor} for {labels.get(road_class, road_class)}" if road_factor != 1 else "") + f" = Rs {tax}.")
    else:
        if not floors:
            raise ValueError("Add at least one floor with its built-up area and use.")
        age = max(0, as_of.year - int(construction_year)) if construction_year else 0
        dep = _depreciation(rules, age)
        residential_arv = Decimal("0")
        floor_rows = []
        for f in floors:
            portion = f.get("portion") or "FULL"
            area = dec(f["builtupSqft"])
            where = f"Floor {f.get('floorNo')}"
            if area <= 0:
                raise ValueError(f"{where}: area must be more than zero.")
            if portion == "ROOFTOP":
                spec = (rules.get("rooftopInstallations") or {}).get(f.get("rooftopType") or "")
                if spec is None:
                    raise ValueError(f"{where}: no rate is set for rooftop installation '{f.get('rooftopType')}'.")
                use = spec.get("usageCode", "COMMERCIAL")
                if use not in rules["taxRatePercentOfArv"]:
                    raise ValueError(f"No tax rate is set for use {use}.")
                mrv, rate_pct = dec(spec["monthlyRatePerSqft"]), dec(rules["taxRatePercentOfArv"][use])
                gross = money(area * mrv * 12 * road_factor)
                floor_tax = money(gross * rate_pct / Decimal("100"))
                floor_rows.append({
                    "kind": "ROOFTOP", "floorNo": f.get("floorNo"), "usageCode": use, "usage": labels.get(use, use),
                    "rooftopType": f.get("rooftopType"), "installation": spec.get("labelEn", f.get("rooftopType")),
                    "builtupSqft": float(area), "monthlyRatePerSqft": float(mrv), "roadFactor": float(road_factor),
                    "grossArv": float(gross), "netArv": float(gross), "depreciationPercent": 0.0, "taxRatePercent": float(rate_pct), "tax": float(floor_tax),
                    "occupancy": "OWNER", "occupancyFactor": 1.0, "construction": "-",
                })
                continue
            use, ctype = f["usageCode"], f["constructionCode"]
            accommodation = bool(f.get("declaredAccommodation"))
            factor_pct = Decimal("100")
            if accommodation:
                acc = rules.get("accommodation") or {}
                use, factor_pct = acc.get("usageCode", "COMMERCIAL"), dec(acc.get("rateFactorPercent", 100))
            try:
                mrv = dec(rules["monthlyRentalValuePerSqft"][zone][use][ctype])
            except KeyError:
                raise ValueError(f"No rental value is set for rate zone {zone}, use {use}, construction {ctype}.")
            mrv = money(mrv * factor_pct / Decimal("100")) if factor_pct != 100 else mrv
            occ = dec(rules["occupancyFactor"].get(f.get("occupancy", "OWNER"), 1))
            if use not in rules["taxRatePercentOfArv"]:
                raise ValueError(f"No tax rate is set for use {use}.")
            rate_pct = dec(rules["taxRatePercentOfArv"][use])
            gross = money(area * mrv * 12 * occ * road_factor)
            net = money(gross * (Decimal("100") - dep) / Decimal("100"))
            floor_tax = money(net * rate_pct / Decimal("100"))
            if use == "RESIDENTIAL":
                residential_arv += net
            floor_rows.append({
                "kind": "FLOOR", "floorNo": f.get("floorNo"), "usageCode": use, "usage": labels.get(use, use), "portion": portion,
                "declaredAccommodation": accommodation, "constructionCode": ctype, "construction": labels.get(ctype, ctype),
                "occupancy": f.get("occupancy", "OWNER"), "builtupSqft": float(area), "monthlyRatePerSqft": float(mrv),
                "occupancyFactor": float(occ), "roadFactor": float(road_factor), "grossArv": float(gross), "depreciationPercent": float(dep),
                "netArv": float(net), "taxRatePercent": float(rate_pct), "tax": float(floor_tax),
            })
        exempt_limit = dec(rules.get("residentialExemptUptoArv", 0))
        small_home = exempt_limit > 0 and Decimal("0") < residential_arv <= exempt_limit
        for row in floor_rows:
            if small_home and row["usageCode"] == "RESIDENTIAL":
                row["tax"] = 0.0
                row["note"] = f"Residential ARV Rs {residential_arv} is within the small-home limit of Rs {exempt_limit}: no property tax."
            tax += dec(row["tax"])
        tax = money(tax)
        lines.extend(floor_rows)
        steps.append(f"Rate zone {zone}. Building age {age} years, so {dep}% depreciation.")
        if road_factor != 1:
            steps.append(f"Road: {labels.get(road_class, road_class)}, rental values x {road_factor}.")
        for row in floor_rows:
            road = f" x {row['roadFactor']} (road)" if row.get("roadFactor", 1) != 1 else ""
            if row["kind"] == "ROOFTOP":
                steps.append(f"Rooftop {row['installation']} ({row['builtupSqft']} sq ft): x Rs {row['monthlyRatePerSqft']} x 12 months{road} "
                             f"= ARV Rs {row['grossArv']}; x {row['taxRatePercent']}% = Rs {row['tax']}.")
                continue
            no = row["floorNo"]
            label = {"PART": f"Part of floor {no}", "COMMON": f"Share of common areas (floor {no})"}.get(row["portion"], f"Floor {no}")
            if row["declaredAccommodation"]:
                label = f"Guest accommodation declared on floor {no}"
            steps.append(
                f"{label} ({row['usage']}, {row['construction']}, {row['occupancy'].lower()}): "
                f"{row['builtupSqft']} sq ft x Rs {row['monthlyRatePerSqft']} x 12 months x {row['occupancyFactor']}{road} "
                f"= Rs {row['grossArv']}; less {row['depreciationPercent']}% = ARV Rs {row['netArv']}; "
                f"x {row['taxRatePercent']}% = Rs {row['tax']}.")
        if small_home:
            steps.append(f"Small home: residential ARV within Rs {exempt_limit}, so no property tax on the residential part.")

    if exemption and dec(exemption.get("percent", 0)) > 0:
        pct = dec(exemption["percent"])
        relief = money(tax * pct / Decimal("100"))
        tax = money(tax - relief)
        lines.append({"kind": "EXEMPTION", "code": exemption.get("code"), "name": exemption.get("nameEn"),
                      "percent": float(pct), "relief": float(relief)})
        steps.append(f"Exemption '{exemption.get('nameEn', exemption.get('code'))}': {pct}% off, saves Rs {relief}.")

    minimum = money(rules.get("minimumAnnualTax", 0))
    if Decimal("0") < tax < minimum:
        lines.append({"kind": "MINIMUM", "minimum": float(minimum), "topUp": float(money(minimum - tax))})
        steps.append(f"Raised to the minimum annual tax of Rs {minimum}.")
        tax = minimum

    components: Dict[str, Decimal] = {tax_component: tax}
    rule = rules.get("setbackPenalty")
    if rule and setback and setback.get("approvedFt") is not None and setback.get("measuredFt") is not None and tax > 0:
        approved, measured, tolerance = dec(setback["approvedFt"]), dec(setback["measuredFt"]), dec(rule.get("toleranceFt", 0))
        shortfall = approved - measured
        if shortfall > tolerance:
            penalty = money(tax * dec(rule.get("percentOfTax", 0)) / Decimal("100"))
            if penalty > 0:
                components["SETBACK_PENALTY"] = penalty
                lines.append({"kind": "SETBACK", "approvedFt": float(approved), "measuredFt": float(measured), "shortfallFt": float(shortfall),
                              "toleranceFt": float(tolerance), "percentOfTax": float(dec(rule.get("percentOfTax", 0))), "amount": float(penalty)})
                steps.append(f"Setback: approved {approved} ft, measured {measured} ft (short by {shortfall} ft, tolerance {tolerance} ft): "
                             f"penalty {dec(rule.get('percentOfTax', 0))}% of Rs {tax} = Rs {penalty} a year until the building is regularised.")
    for c in rules["cess"]:
        amount = money(tax * dec(c["percentOfTax"]) / Decimal("100"))
        components[c["code"]] = amount
        lines.append({"kind": "CESS", "code": c["code"], "name": c.get("labelEn", c["code"]),
                      "percentOfTax": float(dec(c["percentOfTax"])), "amount": float(amount)})
        steps.append(f"{c.get('labelEn', c['code'])}: {dec(c['percentOfTax'])}% of Rs {tax} = Rs {amount}.")
    annual = money(sum(components.values(), Decimal("0")))
    steps.append(f"Total tax for the year: Rs {annual}.")
    return {
        "rateZone": zone,
        "annualTax": annual,
        "components": components,
        "sheet": {"lines": lines, "steps": steps, "rateZone": zone, "annualTax": float(annual),
                  "components": {k: float(v) for k, v in components.items()}},
    }


# ------------------------------------------------------------------------------------------------
# Payments, dues and ageing
# ------------------------------------------------------------------------------------------------

def allocate_payment(amount: Decimal, balances: Dict[str, Decimal], order: Sequence[str]) -> Dict[str, Decimal]:
    """Splits a payment over dues buckets in the configured order (PT-33); the rest is held as ADVANCE."""
    remaining = money(amount)
    if remaining <= 0:
        raise ValueError("Payment amount must be more than zero.")
    if sorted(order) != sorted(DUES_BUCKETS):
        raise ValueError(f"Payment order must list each of {', '.join(DUES_BUCKETS)} exactly once.")
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


def age_outstanding(principal: Decimal, demands: Sequence[Dict], opening_date: Optional[datetime.date],
                    as_of: datetime.date) -> List[Dict]:
    """
    Spreads unpaid principal (arrears + current) over demands, newest first, since payments clear older dues
    first. demands: [{"id","demandNo","period","dueDate","amount"}] newest first. Anything older than every
    demand is the migrated opening arrear, aged from the date it was taken on.
    """
    remaining = money(principal)
    rows: List[Dict] = []
    for d in demands:
        if remaining <= 0:
            break
        part = min(money(d["amount"]), remaining)
        if part > 0:
            rows.append({"demandId": d["id"], "demandNo": d["demandNo"], "period": d["period"], "dueDate": d["dueDate"],
                         "unpaid": part, "ageDays": max(0, (as_of - d["dueDate"]).days)})
            remaining = money(remaining - part)
    if remaining > 0:
        age = max(0, (as_of - opening_date).days) if opening_date else max((r["ageDays"] for r in rows), default=0)
        rows.append({"demandId": None, "demandNo": "OPENING-ARREAR", "period": None, "dueDate": opening_date,
                     "unpaid": remaining, "ageDays": age})
    return rows


def band_for(age_days: int, bands: Sequence[Dict]) -> str:
    """bands: [{"label": "Under 1 year", "maxDays": 365}, ..., {"label": "Over 3 years", "maxDays": None}]"""
    for b in bands:
        if b.get("maxDays") is None or age_days <= int(b["maxDays"]):
            return b["label"]
    return bands[-1]["label"]


def payment_status(bal: Dict[str, Decimal]) -> str:
    older = money(bal.get("ARREAR", 0)) + money(bal.get("PENALTY", 0)) + money(bal.get("FEE", 0))
    if older > 0:
        return "ARREARS"
    if money(bal.get("CURRENT", 0)) > 0:
        return "DUE"
    return "PAID"


# ------------------------------------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------------------------------------

def document_code(doc_type: str, number: str, amount) -> str:
    """Short code printed in the QR so anyone can check a receipt, notice or certificate is genuine (SRS 3.1.1)."""
    msg = f"PTX|{doc_type}|{number}|{money(amount)}".encode("utf-8")
    return hmac.new(_DOC_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:12].upper()


def hash_aadhaar(aadhaar: str) -> Tuple[str, str]:
    """(salted hash, last 4 digits). The full number is never stored (PT-NF-21)."""
    digits = "".join(ch for ch in (aadhaar or "") if ch.isdigit())
    if len(digits) != 12:
        raise ValueError("Aadhaar number must have 12 digits.")
    return hashlib.sha256((_AADHAAR_SALT + digits).encode("utf-8")).hexdigest(), digits[-4:]


def mask_mobile(mobile: Optional[str]) -> Optional[str]:
    if not mobile:
        return mobile
    return ("*" * max(0, len(mobile) - 4)) + mobile[-4:]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
