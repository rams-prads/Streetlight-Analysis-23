"""
End-to-end test of Module 1 (Property Tax & Revenue Management) against a fresh SQLite database.

Run from backend/services/core_service:
    pip install -r requirements.txt -r requirements-dev.txt
    python -m pytest tests/ptx -q

The app is started in-process (lifespan runs the core, water and property tax seeds), then each SRS workflow is
driven through the HTTP API with real sign-ins for each property tax role.
"""
import asyncio
import base64
import datetime
import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="ptx-e2e-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/ptx.db"
os.environ["PTX_STORAGE_DIR"] = os.path.join(_TMP, "storage")
os.environ["WATER_STORAGE_DIR"] = os.path.join(_TMP, "water-storage")
os.environ["ENVIRONMENT"] = "development"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402
from app.api.v1.ptx import cases as cases_module  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
P = "/api/v1/ptx"

ADMIN = ("admin@urban.gov.in", "Admin@123")
OFFICER = ("revenue.officer@gwmc.gov.in", "Ptax@123")
INSPECTOR = ("revenue.inspector@gwmc.gov.in", "Ptax@123")
COLLECTOR = ("bill.collector@gwmc.gov.in", "Ptax@123")
CASHIER = ("ptx.cashier@gwmc.gov.in", "Ptax@123")
COMMISSIONER = ("commissioner@gwmc.gov.in", "Water@123")  # created first by the water seed
CSC = ("csc.operator@gwmc.gov.in", "Water@123")
CITIZEN = ("citizen@gmail.com", "Citizen@123")


class Api:
    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.tokens = {}

    async def login(self, who) -> None:
        r = await self.c.post("/api/v1/auth/signin", json={"userName": who[0], "password": who[1]})
        assert r.status_code == 200, r.text
        self.tokens[who[0]] = r.json()["accessToken"]

    def h(self, who):
        return {"X-Tenant-ID": "GWMC", "Authorization": f"Bearer {self.tokens[who[0]]}"}

    async def get(self, path, who, expect=200, **params):
        r = await self.c.get(P + path, headers=self.h(who), params=params)
        assert r.status_code == expect, f"GET {path} -> {r.status_code}: {r.text}"
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    async def post(self, path, body, who, expect=(200, 201), **params):
        r = await self.c.post(P + path, headers=self.h(who), json=body, params=params)
        expected = expect if isinstance(expect, tuple) else (expect,)
        assert r.status_code in expected, f"POST {path} -> {r.status_code}: {r.text}"
        return r.json()

    async def put(self, path, body, who, expect=200):
        r = await self.c.put(P + path, headers=self.h(who), json=body)
        assert r.status_code == expect, f"PUT {path} -> {r.status_code}: {r.text}"
        return r.json()

    async def patch(self, path, body, who, expect=200):
        r = await self.c.patch(P + path, headers=self.h(who), json=body)
        assert r.status_code == expect, f"PATCH {path} -> {r.status_code}: {r.text}"
        return r.json()


def key():
    return uuid.uuid4().hex


def find(items, **match):
    return next(i for i in items if all(i.get(k) == v for k, v in match.items()))


async def all_rows(api, path, who, **params):
    rows, skip = [], 0
    while True:
        page = await api.get(path, who, skip=skip, limit=100, **params)
        rows += page["items"]
        skip += 100
        if skip >= page["total"]:
            return rows


async def advance(api, no, who, remark, **extra):
    return await api.post(f"/cases/{no}/actions", {"action": "COMPLETE_STEP", "remark": remark, **extra}, who)


async def finalise_after_window(api, no, who):
    """Finalises a case as if the objection period had passed."""
    real_today = cases_module.today
    cases_module.today = lambda: real_today() + datetime.timedelta(days=30)
    try:
        return await api.post(f"/cases/{no}/actions", {"action": "FINALISE", "remark": "No objection received in time"}, who)
    finally:
        cases_module.today = real_today


async def upin_of(api, old_no):
    return (await api.get("/properties", OFFICER, search=old_no))["items"][0]["upin"]


async def scenario():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
            api = Api(client)
            for who in (ADMIN, OFFICER, INSPECTOR, COLLECTOR, CASHIER, COMMISSIONER, CSC, CITIZEN):
                await api.login(who)

            # ---- who can do what ------------------------------------------------------------------------
            me = await api.get("/me", INSPECTOR)
            assert "case.create" in me["permissions"] and "rates.approve" not in me["permissions"]
            assert me["scope"] == "Ward-14" and len(me["wards"]) == 1, me["wards"]
            cashier_me = await api.get("/me", CASHIER)
            assert "payment.collect" in cashier_me["permissions"] and "case.create" not in cashier_me["permissions"]
            await api.get("/rate-tables", CITIZEN, expect=403)
            await api.post("/demand/run", {"period": me["currentPeriod"]}, INSPECTOR, expect=403)
            wards = {w["wardNumber"]: w for w in (await api.get("/me", OFFICER))["wards"]}
            assert {14, 22, 35, 48, 56} <= set(wards)

            # ---- a revenue inspector surveys and files cases, but never collects money or reviews a survey (PT-NF-10) --
            for granted in ("survey.capture", "case.create", "property.edit", "complaint.work", "notice.serve"):
                assert granted in me["permissions"], (granted, me["permissions"])
            for withheld in ("survey.review", "payment.collect", "dayclose.submit", "reports.view", "arrears.manage"):
                assert withheld not in me["permissions"], (withheld, me["permissions"])
            any_upin = (await api.get("/properties", OFFICER, limit=1))["items"][0]["upin"]
            await api.post("/payments", {"upin": any_upin, "amount": 10, "paymentMode": "CASH", "idempotencyKey": key()}, INSPECTOR, expect=403)
            await api.post("/day-close", {"closeDate": datetime.date.today().isoformat(), "declaredCash": 0}, INSPECTOR, expect=403)
            await api.get("/surveys", INSPECTOR, expect=403)

            # ---- a bill collector collects and serves notices, nothing an inspector or officer does (PT-NF-10) --------
            collector_me = await api.get("/me", COLLECTOR)
            for granted in ("payment.collect", "dayclose.submit", "notice.serve", "reports.view.own"):
                assert granted in collector_me["permissions"], (granted, collector_me["permissions"])
            for withheld in ("survey.capture", "survey.review", "property.edit", "case.create", "complaint.work", "reports.view", "arrears.manage"):
                assert withheld not in collector_me["permissions"], (withheld, collector_me["permissions"])
            assert collector_me["scope"] == "Ward-35" and len(collector_me["wards"]) == 1, collector_me["wards"]
            await api.get("/field/sheet", COLLECTOR, wardId=wards[35]["wardId"])  # downloads with notice.serve alone, no survey.capture needed
            await api.get("/surveys", COLLECTOR, expect=403)  # reviewing surveys is the officer's job alone
            own_eff = await api.get("/reports/efficiency", COLLECTOR, by="ward")  # own-only view ignores "by" and never leaks other wards/collectors
            assert all(r["name"] == COLLECTOR[0] for r in own_eff["rows"])
            await api.get("/reports/dcb", COLLECTOR, expect=403)
            defaulters35 = await api.get("/arrears/ageing", COLLECTOR, wardId=wards[35]["wardId"])
            assert all(w["wardNumber"] == 35 for w in defaulters35["byWard"])

            # ---- register: migrated records keep their old numbers (PT-01, PT-05) ------------------------
            register = await api.get("/properties", OFFICER, limit=100)
            assert register["total"] == 25, register["total"]
            old = await api.get("/properties", OFFICER, search="OLD-14-1000")
            assert old["total"] == 1
            upin = old["items"][0]["upin"]
            assert upin.startswith("GWMC-P-")
            scoped = await api.get("/properties", INSPECTOR, limit=100)
            assert scoped["total"] >= 4 and all(r["wardNumber"] == 14 for r in scoped["items"])
            await api.get("/properties/" + (await api.get("/properties", OFFICER, search="OLD-56-1014"))["items"][0]["upin"], INSPECTOR, expect=403)
            pending_loc = await api.get("/properties", OFFICER, locationPending="true")
            assert pending_loc["total"] >= 1
            unpaid = await api.get("/properties", OFFICER, paymentStatus="ARREARS", limit=100)
            assert unpaid["total"] >= 1

            detail = await api.get(f"/properties/{upin}", OFFICER)
            assert detail["assessment"]["status"] == "FINAL" and detail["floors"] and detail["owners"]
            for part in ("dues", "assessments", "demands", "ledger", "history"):
                await api.get(f"/properties/{upin}/{part}", OFFICER)
            lookup = await api.get(f"/lookup/{upin}", OFFICER)
            assert lookup["upin"] == upin and "dues" not in lookup and lookup["ownerNames"]

            # ---- tax calculation preview with plain-language sheet (PT-10, PT-11) -----------------------
            calc = await api.post("/calculate", {"property": {"wardId": wards[14]["wardId"], "siteAreaSqyd": 150, "constructionYear": 2015},
                                                 "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 1200}]},
                                  OFFICER)
            assert calc["annualTax"] > 0 and calc["calculation"]["steps"], calc
            vacant = await api.post("/calculate", {"property": {"propertyType": "VACANT_LAND", "wardId": wards[56]["wardId"], "siteAreaSqyd": 300}}, OFFICER)
            assert vacant["annualTax"] > 0
            await api.post("/calculate", {"property": {"wardId": wards[14]["wardId"], "siteAreaSqyd": 100},
                                          "floors": [{"floorNo": 0, "usageCode": "NOT_A_CODE", "constructionCode": "RCC", "builtupSqft": 500}]},
                           OFFICER, expect=400)

            # ---- new assessment: inspector files, measures, officer approves, citizen objects ---------------
            new_case = await api.post("/cases", {
                "appType": "NEW_ASSESSMENT", "channel": "COUNTER", "consent": True, "applicantName": "P. Sravani", "mobileNumber": "9100000701",
                "property": {"wardId": wards[14]["wardId"], "doorNo": "2-9-77", "address": "2-9-77, New Colony, Subedari", "siteAreaSqyd": 180,
                             "constructionYear": 2025, "latitude": 17.9821, "longitude": 79.5990},
                "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 1000}],
                "owners": [{"fullName": "P. Sravani", "mobileNumber": "9100000701", "aadhaarNumber": "123412341234"}],
                "documents": ["doc-ref-1"]}, INSPECTOR)
            no = new_case["applicationNo"]
            await api.post("/cases", {"appType": "NEW_ASSESSMENT", "consent": False, "property": {"wardId": wards[14]["wardId"]}}, INSPECTOR, expect=400)
            await advance(api, no, INSPECTOR, "Documents in order")
            r = await client.post(f"{P}/cases/{no}/actions", headers=api.h(CASHIER), json={"action": "COMPLETE_STEP", "remark": "should fail"})
            assert r.status_code in (400, 403), r.text
            await advance(api, no, INSPECTOR, "Measured: ground 1000 + first floor 800",
                          floors=[{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 1000},
                                  {"floorNo": 1, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 800, "occupancy": "TENANT"}],
                          photoRefs=["photo-1"], latitude=17.9821, longitude=79.5990)
            approved = await advance(api, no, OFFICER, "Approved as measured")
            assert approved["currentStep"] == "NOTICE" and approved["noticeNo"] and approved["upin"], approved
            new_upin = approved["upin"]
            case = await api.get(f"/cases/{no}", OFFICER)
            assert case["proposedAnnualTax"] > 0 and case["objectionUntil"]
            assert "123412341234" not in str(case)
            await api.post(f"/cases/{no}/actions", {"action": "FINALISE", "remark": "too early"}, OFFICER, expect=400)
            track = await api.get(f"/citizen/cases/{no}", CITIZEN, mobile="9100000701")
            assert track["statusText"] and "mobileNumber" not in str(track)
            await api.get(f"/citizen/cases/{no}", CITIZEN, mobile="9999999999", expect=404)
            await api.post(f"/citizen/cases/{no}/objection", {"mobileNumber": "9100000701", "text": "The first floor is only 600 sq ft, not 800."}, CITIZEN)
            await api.post(f"/cases/{no}/actions", {"action": "FINALISE", "remark": "objection pending"}, OFFICER, expect=400)
            await api.post(f"/cases/{no}/actions", {"action": "DECIDE_OBJECTION", "remark": "Re-measured: 600 sq ft", "objectionUpheld": True,
                                                    "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 1000},
                                                               {"floorNo": 1, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 600,
                                                                "occupancy": "TENANT"}]}, OFFICER)
            lowered = (await api.get(f"/cases/{no}", OFFICER))["proposedAnnualTax"]
            assert lowered < case["proposedAnnualTax"], (lowered, case["proposedAnnualTax"])
            done = await api.post(f"/cases/{no}/actions", {"action": "FINALISE", "remark": "Final"}, OFFICER)
            assert done["status"] == "COMPLETED"
            created = await api.get(f"/properties/{new_upin}", OFFICER)
            assert created["assessment"]["status"] == "FINAL" and created["assessment"]["annualTax"] == lowered
            assert created["owners"][0].get("aadhaarLast4") in (None, "1234") and "123412341234" not in str(created)
            demands = await api.get(f"/properties/{new_upin}/demands", OFFICER)
            assert demands and demands[0]["amount"] > 0

            # ---- seeded use change at the notice stage: finalised after the objection window ---------------
            use_change = find((await api.get("/cases", OFFICER, limit=100))["items"], appType="USE_CHANGE")
            real_today = cases_module.today
            cases_module.today = lambda: real_today() + datetime.timedelta(days=30)
            try:
                uc = await api.post(f"/cases/{use_change['applicationNo']}/actions", {"action": "FINALISE", "remark": "No objection received"}, OFFICER)
            finally:
                cases_module.today = real_today
            assert uc["status"] == "COMPLETED"
            uc_prop = await api.get(f"/properties/{use_change['upin']}", OFFICER)
            assert any(f["usageCode"] == "COMMERCIAL" for f in uc_prop["floors"])
            ledger = await api.get(f"/properties/{use_change['upin']}/ledger", OFFICER)
            assert any(e["txnType"] == "DEMAND_REVISION" for e in ledger), [e["txnType"] for e in ledger]

            # ---- mutation: fee, dues rule, then new owner (PT-14) -----------------------------------------
            mutation = find((await api.get("/cases", OFFICER, limit=100))["items"], appType="MUTATION")
            m_upin = mutation["upin"]
            await advance(api, mutation["applicationNo"], OFFICER, "Sale deed and EC verified")
            blocked = await client.post(f"{P}/cases/{mutation['applicationNo']}/actions", headers=api.h(OFFICER),
                                        json={"action": "COMPLETE_STEP", "remark": "approve"})
            payable = await api.get(f"/properties/{m_upin}/payable", CASHIER)
            assert blocked.status_code == 400 and "fee" in blocked.text.lower(), blocked.text
            await api.post("/payments", {"upin": m_upin, "amount": payable["payToClearAll"], "paymentMode": "CASH", "idempotencyKey": key()}, CASHIER)
            approved = await advance(api, mutation["applicationNo"], OFFICER, "Fee and dues paid, approved")
            assert approved["status"] == "COMPLETED"
            after = await api.get(f"/properties/{m_upin}", OFFICER)
            assert after["owners"][0]["fullName"] == "M. Sravan" and after["ownerHistory"]

            # ---- counter payment, idempotency, receipt verification (PT-31, PT-NF-32) ---------------------
            due_prop = (await api.get("/properties", CASHIER, paymentStatus="ARREARS", limit=100))["items"][0]["upin"]
            quote = await api.get(f"/properties/{due_prop}/payable", CASHIER)
            assert quote["totalDue"] > 0
            k = key()
            r1 = await api.post("/payments", {"upin": due_prop, "amount": 100, "paymentMode": "CASH", "idempotencyKey": k}, CASHIER)
            r2 = await api.post("/payments", {"upin": due_prop, "amount": 100, "paymentMode": "CASH", "idempotencyKey": k}, CASHIER)
            assert r1["receiptNo"] == r2["receiptNo"]
            await api.post("/payments", {"upin": due_prop, "amount": 100, "paymentMode": "CHEQUE", "idempotencyKey": key()}, CASHIER, expect=400)
            cheque = await api.post("/payments", {"upin": due_prop, "amount": 50, "paymentMode": "CHEQUE", "instrumentNo": "000123",
                                                  "instrumentBank": "SBI", "instrumentDate": datetime.date.today().isoformat(),
                                                  "idempotencyKey": key()}, CASHIER)
            verify = await client.get("/api/v1/ptx/public/verify", params={"type": "RECEIPT", "no": r1["receiptNo"], "code": r1["verificationCode"],
                                                                             "tenant": "GWMC"})
            assert verify.status_code == 200 and verify.json()["genuine"] is True, verify.text
            bad = await client.get("/api/v1/ptx/public/verify", params={"type": "RECEIPT", "no": r1["receiptNo"], "code": "WRONG", "tenant": "GWMC"})
            assert bad.json()["genuine"] is False
            printable = await api.get(f"/receipts/{r1['receiptNo']}", CASHIER)
            assert printable["receiptNo"] == r1["receiptNo"]

            # cheque return reverses the payment and adds the charge (PT-35)
            before = (await api.get(f"/properties/{due_prop}/dues", CASHIER))["totalDue"]
            await api.post(f"/receipts/{cheque['receiptNo']}/cheque-return", {"reason": "Insufficient funds"}, CASHIER)
            after_ret = (await api.get(f"/properties/{due_prop}/dues", CASHIER))["totalDue"]
            assert round(after_ret - before, 2) == 350.0, (before, after_ret)

            # receipt cancellation needs approval (maker-checker, PT-35)
            cancel = await api.post(f"/receipts/{r1['receiptNo']}/cancel", {"reason": "Entered against wrong property"}, CASHIER)
            approvals = await api.get("/approvals", OFFICER, status="PENDING")
            appr = find(approvals["items"], id=cancel["approvalId"])
            await api.post(f"/approvals/{appr['id']}/decide", {"decision": "APPROVE", "remark": "Self approval try"}, CASHIER, expect=(400, 403))
            await api.post(f"/approvals/{appr['id']}/decide", {"decision": "APPROVE", "remark": "Verified with counterfoil"}, OFFICER)
            assert (await api.get(f"/receipts/{r1['receiptNo']}", CASHIER))["status"] == "CANCELLED"

            # ---- online payment through the gateway stand-in, including a lost callback (PT-36) ----------
            online_prop = (await api.get("/properties", OFFICER, paymentStatus="ARREARS", limit=100))["items"][-1]["upin"]
            intent = await api.post("/payments/online/initiate", {"upin": online_prop, "amount": 200}, CSC)
            await api.post("/payments/online/stub-gateway", {"orderId": intent["orderId"], "outcome": "SUCCESS"}, CSC)
            status = await api.get(f"/payments/online/{intent['orderId']}", CSC)
            assert status["status"] == "SUCCESS" and status["receipt"]["receiptNo"], status
            lost = await api.post("/payments/online/initiate", {"upin": online_prop, "amount": 10}, CSC)
            await api.post("/payments/online/stub-gateway", {"orderId": lost["orderId"], "outcome": "SUCCESS_NO_CALLBACK"}, CSC)
            assert (await api.get(f"/payments/online/{lost['orderId']}", CSC))["status"] == "INITIATED"
            await api.post("/payments/online/status-check", None, OFFICER)
            assert (await api.get(f"/payments/online/{lost['orderId']}", CSC))["status"] == "SUCCESS"
            failed = await api.post("/payments/online/initiate", {"upin": online_prop, "amount": 10}, CSC)
            await api.post("/payments/online/stub-gateway", {"orderId": failed["orderId"], "outcome": "FAILURE"}, CSC)
            assert (await api.get(f"/payments/online/{failed['orderId']}", CSC))["status"] == "FAILED"

            # ---- day close and reconciliation (PT-37, PT-38) ---------------------------------------------
            today = datetime.date.today().isoformat()
            # the bill collector is scoped to their own ward (Ward-35, PT-NF-10): collecting outside it is refused
            await api.post("/payments", {"upin": due_prop, "amount": 120, "paymentMode": "CASH", "channel": "FIELD",
                                         "idempotencyKey": key()}, COLLECTOR, expect=403)
            collector_due = (await api.get("/properties", OFFICER, paymentStatus="ARREARS", wardId=wards[35]["wardId"], limit=100))["items"][0]["upin"]
            field_rcpt = await api.post("/payments", {"upin": collector_due, "amount": 120, "paymentMode": "CASH", "channel": "FIELD",
                                                     "idempotencyKey": key()}, COLLECTOR)
            # a bill collector's own Receipts screen never shows another collector's or cashier's receipts (PT-NF-10)
            collector_receipts = await api.get("/receipts", COLLECTOR)
            assert [r["receiptNo"] for r in collector_receipts["items"]] == [field_rcpt["receiptNo"]], collector_receipts["items"]
            office_receipts = await api.get("/receipts", OFFICER)
            assert office_receipts["total"] > collector_receipts["total"]
            close = await api.post("/day-close", {"closeDate": today, "declaredCash": 120}, COLLECTOR)
            assert close["systemCash"] == 120 and close["receiptCount"] == 1, close
            await api.post("/day-close", {"closeDate": today, "declaredCash": 120}, COLLECTOR, expect=409)
            await api.post(f"/day-close/{close['id']}/verify", {"receivedCash": 100, "remark": "Rs 20 short"}, CASHIER)
            assert (await api.get("/day-close", CASHIER, status="VERIFIED"))["items"][0]["variance"] == -20
            own = await api.post("/day-close", {"closeDate": today, "declaredCash": 0}, CASHIER)
            await api.post(f"/day-close/{own['id']}/verify", {"receivedCash": 0}, CASHIER, expect=400)
            await api.post(f"/day-close/{own['id']}/verify", {"receivedCash": 0}, OFFICER)
            assert field_rcpt["channel"] == "FIELD"
            statement = await api.get("/reconciliation/stand-in-statement", CASHIER, date=today)
            assert len(statement) >= 2
            recon = await api.post("/reconciliation", {"statementDate": today, "source": "GATEWAY", "rows": statement}, CASHIER)
            assert recon["matched"] == len(statement) and not recon["mismatches"], recon
            recon = await api.post("/reconciliation", {"statementDate": today, "rows": statement + [{"reference": "UNKNOWN-1", "amount": 5}]}, CASHIER)
            assert [m["type"] for m in recon["mismatches"]] == ["NOT_IN_SYSTEM"]

            # ---- schemes: one-time settlement shown before paying (PT-39) ---------------------------------
            ots = None
            for row in (await api.get("/properties", OFFICER, paymentStatus="ARREARS", limit=100))["items"]:
                q = await api.get(f"/properties/{row['upin']}/payable", OFFICER)
                if q["schemes"]:
                    ots = (row["upin"], q)
                    break
            assert ots, "no property with interest qualified for the seeded one-time settlement"
            ots_upin, q = ots
            assert q["saving"] > 0 and q["payToClearAll"] < q["totalDue"]
            receipt = await api.post("/payments", {"upin": ots_upin, "amount": q["payToClearAll"], "paymentMode": "UPI", "idempotencyKey": key()}, CASHIER)
            assert receipt["schemeBenefit"] == q["saving"]
            assert (await api.get(f"/properties/{ots_upin}/dues", OFFICER))["totalDue"] == 0

            # ---- citizen portal: see dues in plain words, pay, certificate (PT-31, PT-40, PT-52) -----------
            acct = await api.get("/citizen/account", CITIZEN, number="OLD-14-1000", mobile="9100000101")
            assert acct["property"]["upin"] == upin and (acct["noDues"] or acct["explanation"])
            assert "mobileMasked" not in str(acct["property"]["owners"])
            rice = await api.get("/citizen/account", CITIZEN, number="OLD-48-1011", mobile="9100000401")
            assert not rice["noDues"] and [l["key"] for l in rice["explanation"]][:2] == ["current", "arrears"], rice["explanation"]
            await api.get("/citizen/account", CITIZEN, number="OLD-14-1000", mobile="9000000000", expect=404)
            # a signed-in citizen keeps their properties: proved once with the owner's mobile, listed every time after
            mine = await api.get("/citizen/my-properties", CITIZEN)
            assert [m["oldAssessmentNo"] for m in mine] == ["1081400234"], mine                     # linked by the demo data
            await api.post("/citizen/my-properties", {"number": "OLD-14-1000", "mobileNumber": "9000000000"}, CITIZEN, expect=404)
            await api.post("/citizen/my-properties", {"number": "OLD-14-1000", "mobileNumber": "9100000101"}, CITIZEN)
            await api.post("/citizen/my-properties", {"number": upin, "mobileNumber": "9100000101"}, CITIZEN)            # adding twice is harmless
            mine = await api.get("/citizen/my-properties", CITIZEN)
            assert [m["upin"] for m in mine][1:] == [upin] and mine[1]["mobileNumber"] == "9100000101" and "totalDue" in mine[1]
            assert upin not in [m["upin"] for m in await api.get("/citizen/my-properties", OFFICER)]                    # each sign-in sees only its own
            r = await client.delete(f"{P}/citizen/my-properties/{upin}", headers=api.h(CITIZEN))
            assert r.status_code == 200, r.text
            assert (await client.delete(f"{P}/citizen/my-properties/{upin}", headers=api.h(CITIZEN))).status_code == 404
            assert len(await api.get("/citizen/my-properties", CITIZEN)) == 1
            await api.get("/citizen/calculation", CITIZEN, number=upin, mobile="9100000101")
            if acct["dues"]["totalDue"] > 0:
                pay = await api.post("/payments/online/initiate", {"upin": upin, "amount": acct["payNow"]}, CITIZEN)
                await api.post("/payments/online/stub-gateway", {"orderId": pay["orderId"], "outcome": "SUCCESS"}, CITIZEN)
            cert = await api.post("/citizen/no-dues-certificate", {"upin": upin, "mobileNumber": "9100000101"}, CITIZEN)
            assert cert["certificateNo"]
            await api.post("/citizen/no-dues-certificate", {"upin": due_prop, "mobileNumber": "9100000101"}, CITIZEN, expect=(400, 404))

            # ---- demand run is resumable and never doubles (PT-30) -----------------------------------------
            period = me["currentPeriod"]
            run1 = await api.post("/demand/run", {"period": period}, OFFICER)
            run2 = await api.post("/demand/run", {"period": period}, OFFICER)
            assert run2.get("raised", 0) == 0, (run1, run2)
            demand_list = await api.get("/demands", OFFICER, period=period, limit=5)
            dn = demand_list["items"][0]["demandNo"]
            notice = await api.get(f"/demands/{dn}", OFFICER)
            assert notice["upiUri"] and notice["verifyPath"]

            # ---- rate revision: proposal needs approval; old versions kept (PT-10, PT-15) ------------------
            tables = await api.get("/rate-tables", OFFICER)
            current = tables["items"][0] if isinstance(tables, dict) else tables[0]
            rules = current["rules"]
            rules["taxRatePercentOfArv"]["COMMERCIAL"] = 26
            await api.post("/rate-tables", {"effectiveFrom": "2020-04-01", "rules": rules, "reason": "Back-dated try"}, OFFICER, expect=400)
            next_fy = datetime.date(datetime.date.today().year + (1 if datetime.date.today().month >= 4 else 0), 4, 1)
            prop_table = await api.post("/rate-tables", {"effectiveFrom": next_fy.isoformat(), "rules": rules, "reason": "Commercial rate revised",
                                                         "orderReference": "G.O. 12/2026"}, OFFICER)
            pending = find((await api.get("/approvals", COMMISSIONER, status="PENDING"))["items"], approvalType="RATE_TABLE")
            await api.post(f"/approvals/{pending['id']}/decide", {"decision": "APPROVE", "remark": "Approved per council resolution"}, OFFICER, expect=(400, 403))
            await api.post(f"/approvals/{pending['id']}/decide", {"decision": "APPROVE", "remark": "Approved per council resolution"}, COMMISSIONER)
            tables = await api.get("/rate-tables", OFFICER)
            listed = tables["items"] if isinstance(tables, dict) else tables
            assert find(listed, id=prop_table["id"])["status"] == "APPROVED" and len(listed) >= 2

            # ---- arrears: interest is idempotent, ageing, notices, field service, recovery (PT-41..PT-44) ----
            i1 = await api.post("/arrears/interest-run", None, OFFICER)
            i2 = await api.post("/arrears/interest-run", None, OFFICER)
            assert i2["charges"] == 0, (i1, i2)
            ageing = await api.get("/arrears/ageing", OFFICER)
            assert ageing["bands"] and ageing["byWard"]
            notices = await api.post("/notices", {"noticeType": "DEMAND", "wardId": wards[14]["wardId"], "minDue": 1}, OFFICER)
            sheet = await api.get("/field/sheet", INSPECTOR, wardId=wards[14]["wardId"])
            assert sheet["properties"] and "noticesToServe" in sheet
            assert sheet["noticesToServe"], sheet
            n0 = sheet["noticesToServe"][0]["noticeNo"]
            item = {"noticeNo": n0, "served": True, "latitude": 17.98, "longitude": 79.59, "photoRef": "p1", "clientRef": key()}
            s1 = await api.post("/field/notice-service", {"items": [item]}, INSPECTOR)
            s2 = await api.post("/field/notice-service", {"items": [item]}, INSPECTOR)
            assert s1["recorded"] == 1 and s2["recorded"] == 1, (s1, s2)
            assert (await api.get(f"/notices/{n0}", OFFICER))["serviceStatus"] == "SERVED"
            assert notices
            await api.post("/recovery/run", None, OFFICER)
            recovery = await api.get("/recovery", OFFICER)
            assert recovery["items"], "no recovery case opened for the large defaulters"
            if True:
                await api.post(f"/recovery/{recovery['items'][0]['caseNo']}/advance", {"remark": "Final notice served"}, OFFICER)

            # waiver above the officer limit goes to the commissioner (PT-41, approval limits)
            w_upin = (await api.get("/properties", OFFICER, paymentStatus="ARREARS", limit=100))["items"][0]["upin"]
            w_dues = await api.get(f"/properties/{w_upin}/dues", OFFICER)
            assert w_dues["interest"] > 0, w_dues
            if True:
                w = await api.post(f"/properties/{w_upin}/waivers", {"kind": "WAIVER", "bucket": "PENALTY", "amount": min(w_dues["interest"], 10),
                                                                      "reason": "Council resolution 4/2026"}, OFFICER)
                await api.post(f"/approvals/{w['approvalId']}/decide", {"decision": "APPROVE", "remark": "Within limit"}, OFFICER, expect=(400, 403))
                await api.post(f"/approvals/{w['approvalId']}/decide", {"decision": "APPROVE", "remark": "Within limit"}, COMMISSIONER)
                assert (await api.get(f"/properties/{w_upin}/dues", OFFICER))["interest"] < w_dues["interest"]

            # ---- property registration and identification: a new property gets its UPIN by linking to a GIS
            # parcel from the office, with no prior field visit needed (PT-01, PTX-P01) -----------------------
            await api.get("/gis/parcels", CASHIER, expect=403)  # not someone who files applications
            ward56_parcels = await api.get("/gis/parcels", OFFICER, wardId=wards[56]["wardId"])
            assert ward56_parcels and all(p["wardNumber"] == 56 for p in ward56_parcels)
            picked = ward56_parcels[0]
            nearby = await api.get("/gis/parcels", OFFICER, lat=picked["lat"], lng=picked["lng"])
            assert nearby[0]["footprintId"] == picked["footprintId"] and nearby[0]["distanceM"] == 0, nearby[0]  # nearest first
            reg_case = await api.post("/cases", {
                "appType": "NEW_ASSESSMENT", "channel": "COUNTER", "consent": True, "applicantName": "D. Ramesh", "mobileNumber": "9100000801",
                "property": {"wardId": wards[56]["wardId"], "doorNo": "4-1-10", "address": "4-1-10, Near the tank bund", "siteAreaSqyd": 140,
                             "constructionYear": 2024, "footprintId": picked["footprintId"]},
                "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 950}],
                "owners": [{"fullName": "D. Ramesh", "mobileNumber": "9100000801"}], "documents": ["doc-ref-reg"]}, OFFICER)
            reg_no = reg_case["applicationNo"]
            await advance(api, reg_no, OFFICER, "Documents in order")
            await advance(api, reg_no, OFFICER, "Site matches the map parcel", floors=[{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 950}])
            reg_approved = await advance(api, reg_no, OFFICER, "Approved; parcel confirmed on the map")
            reg_upin = reg_approved["upin"]
            registered = await api.get(f"/properties/{reg_upin}", OFFICER)
            assert registered["footprintId"] == picked["footprintId"]
            assert (registered["latitude"], registered["longitude"]) == (picked["lat"], picked["lng"]) and not registered["locationPending"]
            # a footprint already linked to a property cannot be claimed again
            still_free = await api.get("/gis/parcels", OFFICER, wardId=wards[56]["wardId"])
            assert picked["footprintId"] not in [p["footprintId"] for p in still_free]
            await api.post("/cases", {"appType": "NEW_ASSESSMENT", "consent": True, "applicantName": "Someone else",
                                      "property": {"wardId": wards[56]["wardId"], "address": "same parcel again", "siteAreaSqyd": 100,
                                                   "footprintId": picked["footprintId"]},
                                      "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 500}],
                                      "owners": [{"fullName": "Someone else"}]}, OFFICER, expect=409)

            # ---- field survey offline sync, review opens a case (PT-06, PT-50) ----------------------------
            unassessed = [f for f in (await api.get("/gis/layers", OFFICER))["unassessed"] if f.get("wardNumber") == 14]
            assert unassessed, "no unassessed footprints in ward 14"
            up = await client.post(f"{P}/uploads", headers=api.h(INSPECTOR), files={"file": ("p.png", PNG, "image/png")})
            assert up.status_code == 201, up.text
            ref = up.json()["ref"]
            survey = {"clientRef": key(), "surveyType": "NEW_BUILDING", "footprintId": unassessed[0]["footprintId"], "occupantName": "K. Lakshmi",
                      "address": "2-9-90, Subedari", "doorNo": "2-9-90", "siteAreaSqyd": 120, "photoRefs": [ref], "latitude": 17.98, "longitude": 79.59,
                      "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 900}]}
            s1 = await api.post("/field/surveys", {"surveys": [survey]}, INSPECTOR)
            s2 = await api.post("/field/surveys", {"surveys": [survey]}, INSPECTOR)
            assert s1["stored"] == 1 and s2["duplicates"] == 1
            no_photo = {**survey, "clientRef": key(), "photoRefs": []}
            assert (await api.post("/field/surveys", {"surveys": [no_photo]}, INSPECTOR))["errors"] == 1
            review = await api.get("/surveys", OFFICER)
            sid = find(review["items"], id=s1["results"][0]["surveyId"])["id"]
            opened = await api.post(f"/surveys/{sid}/decision", {"outcome": "OPEN_CASE", "remark": "Building not on the register"}, OFFICER)
            assert opened["applicationNo"]

            # ---- corrections that do not change tax, and tenants (PT-07, PT-13) -----------------------------
            fix_upin = await upin_of(api, "OLD-22-1018")
            await api.patch(f"/properties/{fix_upin}", {"reason": "Door number corrected per site visit", "doorNo": "3-7-120/A"}, OFFICER)
            history = await api.get(f"/properties/{fix_upin}/history", OFFICER)
            assert any(h["field"] == "door_no" and h["newValue"] == "3-7-120/A" for h in history), history
            await api.put(f"/properties/{fix_upin}/occupiers", {"reason": "Tenant moved in",
                                                                 "occupiers": [{"fullName": "R. Tenant", "mobileNumber": "9100000999"}]}, OFFICER)
            assert (await api.get(f"/properties/{fix_upin}", OFFICER))["occupiers"][0]["fullName"] == "R. Tenant"
            await api.patch(f"/properties/{fix_upin}", {"reason": "Trying a change", "doorNo": "x"}, CASHIER, expect=403)

            # ---- a case rejected before the notice (PT-18); only one open case per property -------------------
            rej_upin = await upin_of(api, "OLD-48-1012")
            rej = await api.post("/cases", {"appType": "REASSESSMENT", "upin": rej_upin, "consent": True, "reason": "Owner says area is wrong",
                                            "property": {"siteAreaSqyd": 170}}, OFFICER)
            dup = await client.post(f"{P}/cases", headers=api.h(OFFICER), json={"appType": "REASSESSMENT", "upin": rej_upin, "consent": True})
            assert dup.status_code == 409, dup.text
            await api.post(f"/cases/{rej['applicationNo']}/actions", {"action": "REJECT", "remark": "No supporting documents"}, OFFICER)
            assert (await api.get(f"/cases/{rej['applicationNo']}", OFFICER))["status"] == "REJECTED"

            # ---- exemption claim needs its document (PT-20) ---------------------------------------------------
            school = await upin_of(api, "OLD-35-1007")
            school_tax = (await api.get(f"/properties/{school}", OFFICER))["assessment"]["annualTax"]
            await api.post("/cases", {"appType": "EXEMPTION", "upin": school, "consent": True, "property": {"exemptionCode": "CHARITABLE_EDUCATION"}},
                           OFFICER, expect=400)
            ex = await api.post("/cases", {"appType": "EXEMPTION", "upin": school, "consent": True, "documents": ["trust-deed"],
                                           "property": {"exemptionCode": "CHARITABLE_EDUCATION"}}, OFFICER)
            await advance(api, ex["applicationNo"], OFFICER, "Trust registration verified")
            await advance(api, ex["applicationNo"], OFFICER, "Exemption approved")
            assert (await finalise_after_window(api, ex["applicationNo"], OFFICER))["status"] == "COMPLETED"
            exempt = await api.get(f"/properties/{school}", OFFICER)
            assert exempt["exemptionCode"] == "CHARITABLE_EDUCATION" and exempt["assessment"]["annualTax"] < school_tax, exempt["assessment"]

            # ---- subdivision: parts get new UPINs, dues split by area, parent retired (PT-16) -----------------
            parent = await upin_of(api, "OLD-35-1010")
            parent_due = (await api.get(f"/properties/{parent}/dues", OFFICER))["totalDue"]
            sub = await api.post("/cases", {"appType": "SUBDIVISION", "upin": parent, "consent": True, "documents": ["partition-deed"], "parts": [
                {"property": {"doorNo": "1-12-15/1", "siteAreaSqyd": 120},
                 "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 900}]},
                {"property": {"doorNo": "1-12-15/2", "siteAreaSqyd": 80},
                 "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 600}],
                 "owners": [{"fullName": "S. Venu Jr", "mobileNumber": "9100000888"}]}]}, OFFICER)
            for remark in ("Partition deed verified", "Both parts measured", "Approved"):
                await advance(api, sub["applicationNo"], OFFICER, remark)
            done_sub = await finalise_after_window(api, sub["applicationNo"], OFFICER)
            kids = done_sub["result"]["newUpins"]
            assert len(kids) == 2
            assert (await api.get(f"/properties/{parent}", OFFICER))["status"] == "RETIRED"
            assert (await api.get(f"/properties/{parent}/dues", OFFICER))["totalDue"] == 0
            kid_dues = [(await api.get(f"/properties/{k}/dues", OFFICER))["totalDue"] for k in kids]
            assert sum(kid_dues) >= parent_due + 500 - 0.05 and kid_dues[0] > kid_dues[1], (kid_dues, parent_due)

            # ---- amalgamation: dues must be cleared first, then one new UPIN (PT-17) ---------------------------
            a1, a2 = await upin_of(api, "OLD-56-1015"), await upin_of(api, "OLD-56-1016")
            am = await api.post("/cases", {"appType": "AMALGAMATION", "upins": [a1, a2], "consent": True, "documents": ["deed"],
                                           "property": {"doorNo": "4-2-31/60", "address": "4-2-31/60, Chowrasta, Warangal", "siteAreaSqyd": 320},
                                           "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 2400}],
                                           "owners": [{"fullName": "D. Rajamma", "mobileNumber": "9100000502", "sharePercent": 50},
                                                      {"fullName": "K. Yakub", "mobileNumber": "9100000503", "sharePercent": 50}]}, OFFICER)
            await advance(api, am["applicationNo"], OFFICER, "Deed verified")
            await advance(api, am["applicationNo"], OFFICER, "Measured")
            r = await client.post(f"{P}/cases/{am['applicationNo']}/actions", headers=api.h(OFFICER), json={"action": "COMPLETE_STEP", "remark": "Approve"})
            assert r.status_code == 400 and "cleared" in r.text, r.text
            for u in (a1, a2):
                q = await api.get(f"/properties/{u}/payable", CASHIER)
                if q["totalDue"] > 0:
                    await api.post("/payments", {"upin": u, "amount": q["payToClearAll"], "paymentMode": "CASH", "idempotencyKey": key()}, CASHIER)
            await advance(api, am["applicationNo"], OFFICER, "Dues cleared, approved")
            merged = (await finalise_after_window(api, am["applicationNo"], OFFICER))["result"]
            assert merged["newUpin"] and (await api.get(f"/properties/{a1}", OFFICER))["status"] == "RETIRED"
            assert len((await api.get(f"/properties/{merged['newUpin']}", OFFICER))["owners"]) == 2

            # ---- excess payment held as advance, refunded after approval (PT-40) -------------------------------
            paid_upin = await upin_of(api, "OLD-14-1000")
            due_now = (await api.get(f"/properties/{paid_upin}/dues", CASHIER))["totalDue"]
            await api.post("/payments", {"upin": paid_upin, "amount": due_now + 500, "paymentMode": "CASH", "idempotencyKey": key()}, CASHIER)
            held = await api.get(f"/properties/{paid_upin}/dues", CASHIER)
            assert held["advanceHeld"] == 500, held
            await api.post(f"/properties/{paid_upin}/refunds", {"amount": 900, "mode": "PAY", "reason": "Paid twice by mistake"}, CASHIER, expect=400)
            refund = await api.post(f"/properties/{paid_upin}/refunds", {"amount": 300, "mode": "PAY", "reason": "Paid twice by mistake"}, CASHIER)
            await api.post(f"/approvals/{refund['approvalId']}/decide", {"decision": "APPROVE", "remark": "Bank details verified"}, OFFICER)
            assert (await api.get(f"/properties/{paid_upin}/dues", CASHIER))["advanceHeld"] == 200

            # ---- general revision with the approved new rate table (PT-15) -------------------------------------
            rev = await api.post("/revision/run", {"rateTableId": prop_table["id"], "wardIds": [wards[22]["wardId"]]}, OFFICER)
            rev_again = await api.post("/revision/run", {"rateTableId": prop_table["id"], "wardIds": [wards[22]["wardId"]]}, OFFICER)
            assert rev["reassessed"] >= 1 and rev_again["reassessed"] == 0 and rev_again["wards"][0]["status"] == "ALREADY_DONE", (rev, rev_again)
            jobs = await api.get("/jobs", OFFICER)
            assert jobs

            # ---- survey that matches the record; map footprint sent for verification (PT-06, PT-50) ------------
            v_upin = scoped["items"][0]["upin"]
            match = {"clientRef": key(), "surveyType": "VERIFY", "upin": v_upin, "photoRefs": ["p"], "latitude": 17.98, "longitude": 79.59}
            stored = await api.post("/field/surveys", {"surveys": [match]}, INSPECTOR)
            sid2 = stored["results"][0]["surveyId"]
            # the inspector who captured it cannot also be its checker - that is the officer's job alone (PT-NF-10)
            await api.post(f"/surveys/{sid2}/decision", {"outcome": "MATCHES_RECORD", "remark": "Same as record"}, INSPECTOR, expect=403)
            await api.post(f"/surveys/{sid2}/decision", {"outcome": "MATCHES_RECORD", "remark": "Same as record"}, OFFICER)
            await api.post(f"/surveys/{sid2}/decision", {"outcome": "CLOSE", "remark": "again"}, OFFICER, expect=400)
            other = [f for f in (await api.get("/gis/layers", OFFICER))["unassessed"] if f["status"] == "NONE"]
            assert other
            await api.post(f"/gis/footprints/{other[0]['footprintId']}/verify", None, OFFICER)

            # ---- even an officer, who may also capture a survey, cannot review their own (PT-NF-10) -----------
            self_match = {"clientRef": key(), "surveyType": "VERIFY", "upin": scoped["items"][1]["upin"], "photoRefs": ["p"], "latitude": 17.98, "longitude": 79.59}
            self_stored = await api.post("/field/surveys", {"surveys": [self_match]}, OFFICER)
            self_sid = self_stored["results"][0]["surveyId"]
            own_review = await client.post(f"{P}/surveys/{self_sid}/decision", headers=api.h(OFFICER),
                                           json={"outcome": "MATCHES_RECORD", "remark": "Self review"})
            assert own_review.status_code == 400 and "own survey" in own_review.text, own_review.text

            # ---- reports and the commissioner dashboard (PT-45..PT-49) --------------------------------------
            for level in ("property", "ward", "zone", "city"):
                dcb = await api.get("/reports/dcb", OFFICER, level=level)
                assert "rows" in dcb or "items" in dcb
            for by in ("ward", "zone", "collector"):
                await api.get("/reports/efficiency", OFFICER, by=by, view="YTD")
            await api.get("/reports/daily-collection", OFFICER)
            await api.get("/reports/account-heads", OFFICER)
            dash = await api.get("/dashboard/commissioner", COMMISSIONER)
            assert dash
            await api.get("/gis/heat", OFFICER, level="ward")
            await api.get("/gis/tax-gap", OFFICER)

            # ---- settings are versioned and never back-dated; audit trail (PT-NF-13) -----------------------
            await api.post("/admin/settings", {"key": "interest", "value": {"percentPerMonth": 1.5, "graceDays": 0},
                                               "effectiveFrom": "2020-01-01", "reason": "Back-dated"}, ADMIN, expect=400)
            await api.post("/admin/settings", {"key": "interest", "value": {"percentPerMonth": 1.5, "graceDays": 0},
                                               "effectiveFrom": next_fy.isoformat(), "reason": "Notified change"}, ADMIN)
            await api.post("/admin/settings", {"key": "interest", "value": {"percentPerMonth": 1.5}, "effectiveFrom": next_fy.isoformat(),
                                               "reason": "Notified change"}, OFFICER, expect=403)
            audit = await api.get("/admin/audit", ADMIN)
            assert audit["total"] > 0
            events = await api.get("/admin/events", ADMIN)
            assert events["counts"].get("payment.received", 0) > 0 and events["events"]["items"]
            await api.get("/admin/api-log", ADMIN)
            await api.get("/admin/notifications", ADMIN)
            export = await client.get(f"{P}/export/register", headers=api.h(ADMIN), params={"format": "csv"})
            assert export.status_code == 200 and "upin" in export.text.lower()

            # migration: a bad record is listed, never dropped (SRS 3.6.2)
            mig = await api.post("/migration/properties", {"arrearsAsOf": "2025-04-01", "records": [
                {"oldAssessmentNo": "OLD-T-1", "ownerName": "Test Owner", "address": "1-1, Test", "wardNumber": 22, "siteAreaSqyd": 100,
                 "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 500, "openingArrears": 1200},
                {"oldAssessmentNo": "OLD-T-2", "ownerName": "Bad Ward", "address": "x", "wardNumber": 999}]}, ADMIN)
            assert len(mig["created"]) == 1 and len(mig["exceptions"]) == 1

            # ---- valuation: road class, part-use, rooftop, guest accommodation, setback penalty (PT-12, PT-31..PT-33) ----
            year = datetime.date.today().year
            ward14 = wards[14]["wardId"]

            async def tax(floors, **prop):
                body = {"property": {"wardId": ward14, "siteAreaSqyd": 150, "constructionYear": year, **prop}, "floors": floors}
                return await api.post("/calculate", body, OFFICER)

            home = {"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 1000}
            base = await tax([home])
            assert base["annualTax"] == 3304.80 and base["components"] == {"PROPERTY_TAX": 3060.0, "LIBRARY_CESS": 244.8}, base
            main = await tax([home], roadClass="MAIN_ROAD")          # rental value x 1.15
            assert main["components"]["PROPERTY_TAX"] == 3519.0 and main["annualTax"] == 3800.52, main
            lane = await tax([home], roadClass="LANE")               # x 0.90
            assert lane["components"]["PROPERTY_TAX"] == 2754.0, lane
            assert any("Road" in step for step in main["calculation"]["steps"])
            await api.post("/calculate", {"property": {"wardId": ward14, "siteAreaSqyd": 150, "roadClass": "HIGHWAY"}, "floors": [home]}, OFFICER, expect=400)

            # part of a floor used for a shop: two rows on the same floor, each at its own use
            part = await tax([{**home, "builtupSqft": 700}, {"floorNo": 0, "usageCode": "COMMERCIAL", "constructionCode": "RCC", "builtupSqft": 300, "portion": "PART"}])
            assert part["components"]["PROPERTY_TAX"] == 5742.0, part
            same_twice = {"property": {"wardId": ward14, "siteAreaSqyd": 150}, "floors": [home, home]}
            assert "same row twice" in (await api.post("/calculate", same_twice, OFFICER, expect=400))["detail"]

            # self-declared guest accommodation is charged at the notified accommodation use and rate factor (60% of commercial)
            guest = await tax([{**home, "builtupSqft": 800}, {**home, "builtupSqft": 200, "portion": "PART", "declaredAccommodation": True}])
            assert guest["components"]["PROPERTY_TAX"] == 3888.0, guest
            assert any("Guest accommodation declared" in step for step in guest["calculation"]["steps"])

            # rooftop installation: its own rate, no wear deduction, taxed at the commercial rate
            tower = await tax([home, {"floorNo": 1, "builtupSqft": 100, "portion": "ROOFTOP", "rooftopType": "MOBILE_TOWER"}])
            assert tower["components"]["PROPERTY_TAX"] == 9060.0, tower
            await api.post("/calculate", {"property": {"wardId": ward14, "siteAreaSqyd": 150}, "floors": [home, {"floorNo": 1, "builtupSqft": 50, "portion": "ROOFTOP",
                                                                                                                   "rooftopType": "FUNFAIR"}]}, OFFICER, expect=400)
            await api.post("/calculate", {"property": {"wardId": ward14, "siteAreaSqyd": 150},
                                          "floors": [{"floorNo": 1, "builtupSqft": 100, "portion": "ROOFTOP", "rooftopType": "MOBILE_TOWER"}]}, OFFICER, expect=400)

            # setback: short by more than the 1 ft tolerance adds 10% of the tax as its own component
            short = await tax([home], approvedSetbackFt=10, measuredSetbackFt=6)
            assert short["components"]["SETBACK_PENALTY"] == 306.0 and short["annualTax"] == 3610.80, short
            assert (await tax([home], approvedSetbackFt=10, measuredSetbackFt=9.5))["annualTax"] == 3304.80
            assert "SETBACK_PENALTY" not in (await tax([home], approvedSetbackFt=10))["components"]

            # the penalty reaches the property, the assessment and the bill through a reassessment with the inspection result
            pen = await upin_of(api, "OLD-35-1008")
            re = await api.post("/cases", {"appType": "REASSESSMENT", "upin": pen, "consent": True, "reason": "Setback checked on site",
                                           "property": {"approvedSetbackFt": 10, "measuredSetbackFt": 5}}, OFFICER)
            assert "Setback" in " ".join(re["calculation"]["steps"])
            for remark in ("Documents verified", "Measured: setback is only 5 ft"):
                await advance(api, re["applicationNo"], OFFICER, remark)
            await advance(api, re["applicationNo"], OFFICER, "Approved")
            assert (await finalise_after_window(api, re["applicationNo"], OFFICER))["status"] == "COMPLETED"
            penalised = await api.get(f"/properties/{pen}", OFFICER)
            assert penalised["measuredSetbackFt"] == 5 and "SETBACK_PENALTY" in penalised["assessment"]["components"], penalised["assessment"]["components"]
            assert penalised["roadClass"] in ("STREET", "LANE", "MAIN_ROAD")

            # ---- apartment building: every flat becomes its own property with its share of site and common areas (PT-07) ----
            flats = [{"unitNo": "A1", "floors": [{"floorNo": 1, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 900}],
                      "owners": [{"fullName": "P. Anil", "mobileNumber": "9100000711"}]},
                     {"unitNo": "A2", "floors": [{"floorNo": 1, "usageCode": "RESIDENTIAL", "constructionCode": "RCC", "builtupSqft": 600}],
                      "owners": [{"fullName": "S. Bhargavi", "mobileNumber": "9100000712"}]}]
            building = {"wardId": ward14, "doorNo": "2-9-200", "address": "2-9-200, Subedari Main Road", "siteAreaSqyd": 300, "constructionYear": year, "roadClass": "MAIN_ROAD"}
            apt_body = {"appType": "APARTMENT", "consent": True, "complexName": "Lakshmi Towers", "commonAreaSqft": 300, "property": building, "units": flats,
                        "documents": ["plan"]}
            await api.post("/cases", {**apt_body, "units": flats[:1]}, OFFICER, expect=400)                                   # needs two units
            await api.post("/cases", {**apt_body, "units": [flats[0], {**flats[1], "unitNo": "a1"}]}, OFFICER, expect=400)      # duplicate unit number
            await api.post("/cases", {**apt_body, "complexName": ""}, OFFICER, expect=400)
            apt = await api.post("/cases", apt_body, INSPECTOR)
            assert apt["appType"] == "APARTMENT" and [s["code"] for s in apt["steps"]] == ["DOC_CHECK", "FIELD_INSPECTION", "APPROVAL"]
            expected = sum(x["annualTax"] for x in [await tax(u["floors"] + [{**u["floors"][0], "portion": "COMMON", "builtupSqft": 300 * a / 1500}], roadClass="MAIN_ROAD",
                                                               siteAreaSqyd=300 * a / 1500)
                                                    for u, a in zip(flats, (900, 600))])
            assert abs(apt["proposedAnnualTax"] - expected) < 0.02, (apt["proposedAnnualTax"], expected)
            await advance(api, apt["applicationNo"], INSPECTOR, "Plan and sale agreements verified")
            await advance(api, apt["applicationNo"], INSPECTOR, "All units measured on site")
            done_apt = await advance(api, apt["applicationNo"], OFFICER, "Approved")
            assert done_apt["status"] == "COMPLETED", done_apt
            units = (await api.get(f"/cases/{apt['applicationNo']}", OFFICER))["result"]["newUpins"]
            assert len(units) == 2
            found = await api.get("/properties", OFFICER, search="Lakshmi Towers")
            assert found["total"] == 2 and {r["unitNo"] for r in found["items"]} == {"A1", "A2"}
            flat_a = await api.get(f"/properties/{units[0]}", OFFICER)
            assert flat_a["complexName"] == "Lakshmi Towers" and flat_a["unitNo"] in ("A1", "A2") and flat_a["assessment"]["status"] == "FINAL"
            assert any(f["portion"] == "COMMON" for f in flat_a["floors"]), flat_a["floors"]
            assert abs(flat_a["siteAreaSqyd"] - (180 if flat_a["unitNo"] == "A1" else 120)) < 0.01
            assert abs(sum([(await api.get(f"/properties/{u}", OFFICER))["assessment"]["annualTax"] for u in units]) - apt["proposedAnnualTax"]) < 0.02
            assert (await api.get(f"/properties/{units[0]}/demands", OFFICER)), "bills are raised for each flat"
            notice_page = await api.get("/notices", OFFICER, search=units[1], type="ASSESSMENT")
            assert notice_page["total"] == 1

            # ---- demolition: the property is closed, later bills reversed, earlier dues stay (PT-17) ----
            now_d = datetime.date.today()
            gone = await upin_of(api, "OLD-56-1014")
            before = await api.get(f"/properties/{gone}", OFFICER)
            demo_body = {"appType": "DEMOLITION", "upin": gone, "consent": True, "effectiveFrom": (now_d - datetime.timedelta(days=5)).isoformat(),
                         "reason": "Building pulled down for redevelopment"}
            await api.post("/cases", demo_body, OFFICER, expect=400)                                                    # needs proof
            await api.post("/cases", {**demo_body, "documents": ["demolition-permission"], "effectiveFrom": None}, OFFICER, expect=400)  # needs the date
            await api.post("/cases", {**demo_body, "documents": ["x"], "effectiveFrom": (now_d - datetime.timedelta(days=365 * 6)).isoformat()}, OFFICER, expect=400)
            demo = await api.post("/cases", {**demo_body, "documents": ["demolition-permission", "site-photo"]}, OFFICER)
            assert [x["code"] for x in demo["steps"]] == ["DOC_CHECK", "FIELD_INSPECTION", "APPROVAL"] and demo["proposedAnnualTax"] is None
            await advance(api, demo["applicationNo"], OFFICER, "Demolition permission verified")
            await advance(api, demo["applicationNo"], OFFICER, "Site visited: plot is clear")
            demolished = await advance(api, demo["applicationNo"], OFFICER, "Approved")
            assert demolished["status"] == "COMPLETED", demolished
            closed = await api.get(f"/properties/{gone}", OFFICER)
            assert closed["status"] == "RETIRED" and closed["retiredReason"] == "DEMOLISHED" and closed["assessment"]["annualTax"] == 0, closed["assessment"]
            assert closed["dues"]["current"] <= 0.001, closed["dues"]
            assert closed["dues"]["netPayable"] <= before["dues"]["netPayable"]
            assert "DEMOLITION" in [a["kind"] for a in await api.get(f"/properties/{gone}/assessments", OFFICER)]
            again = await client.post(f"{P}/cases", headers=api.h(OFFICER), json=demo_body | {"documents": ["x"]})
            assert again.status_code == 400 and "retired" in again.text.lower(), again.text
            done_demo = await api.get(f"/cases/{demo['applicationNo']}", OFFICER)
            assert done_demo["result"]["demolishedOn"] == demo_body["effectiveFrom"]

            # ---- back-assessment: an under-assessed property is corrected for earlier years, with the Commissioner's approval (PT-11) ----
            under = await upin_of(api, "OLD-14-1002")
            dues_before = (await api.get(f"/properties/{under}/dues", OFFICER))["totalDue"]
            two_years = now_d.replace(year=now_d.year - 2)
            back_body = {"appType": "BACK_ASSESSMENT", "upin": under, "consent": True, "effectiveFrom": two_years.isoformat(),
                         "reason": "Built-up area on site is larger than the area on record",
                         "floors": [{"floorNo": 0, "usageCode": "RESIDENTIAL", "constructionCode": "TILED", "builtupSqft": 1100}]}
            await api.post("/cases", {**back_body, "reason": "wrong"}, OFFICER, expect=400)
            too_old = await client.post(f"{P}/cases", headers=api.h(OFFICER), json={**back_body, "effectiveFrom": now_d.replace(year=now_d.year - 5).isoformat()})
            assert too_old.status_code == 400 and "reach back only 3 years" in too_old.text, too_old.text
            back = await api.post("/cases", back_body, OFFICER)
            assert back["appType"] == "BACK_ASSESSMENT" and back["proposedAnnualTax"] > 0
            await advance(api, back["applicationNo"], OFFICER, "Records checked")
            await advance(api, back["applicationNo"], OFFICER, "Remeasured: 1100 sq ft")
            refused = await client.post(f"{P}/cases/{back['applicationNo']}/actions", headers=api.h(OFFICER), json={"action": "COMPLETE_STEP", "remark": "Approve"})
            assert refused.status_code == 400 and "Commissioner" in refused.text, refused.text
            await advance(api, back["applicationNo"], COMMISSIONER, "Approved: charge the earlier years")
            back_done = await finalise_after_window(api, back["applicationNo"], OFFICER)
            assert back_done["status"] == "COMPLETED" and back_done["result"]["demandsRaised"] >= 1, back_done
            kinds = {a["kind"]: a["status"] for a in await api.get(f"/properties/{under}/assessments", OFFICER)}
            assert kinds["BACK_ASSESSMENT"] == "FINAL" and kinds["MIGRATION"] == "REPLACED", kinds
            periods = {d["period"] for d in await api.get(f"/properties/{under}/demands", OFFICER)}
            assert any(pd < "2025-26" for pd in periods), periods                         # bills raised for the earlier years
            assert (await api.get(f"/properties/{under}/dues", OFFICER))["totalDue"] > dues_before

            # ---- bill correction: needs approval, never edits the bill, an overpayment becomes advance (PT-19) ----
            fixed_upin = await upin_of(api, "OLD-14-1001")
            bill = (await api.get(f"/properties/{fixed_upin}/demands", OFFICER))[0]
            adv_before = (await api.get(f"/properties/{fixed_upin}/dues", OFFICER))["advanceHeld"]
            await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": -999999999, "reason": "Clerical error in the area"}, OFFICER, expect=400)
            await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": 0, "reason": "Clerical error in the area"}, OFFICER, expect=422)
            await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": -50, "reason": "Clerical error in the area"}, INSPECTOR, expect=403)
            corr = await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": -50, "reason": "Clerical error in the area"}, OFFICER)
            await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": -10, "reason": "Another change please"}, OFFICER, expect=409)
            await api.post(f"/approvals/{corr['approvalId']}/decide", {"decision": "APPROVE", "remark": "Own request"}, OFFICER, expect=400)
            pending = find((await api.get("/approvals", COMMISSIONER, status="PENDING", type="DEMAND_CORRECTION"))["items"], id=corr["approvalId"])
            assert pending["details"]["billAfter"] == pending["details"]["billNow"] - 50
            await api.post(f"/approvals/{corr['approvalId']}/decide", {"decision": "APPROVE", "remark": "Verified against the site record"}, COMMISSIONER)
            ledger_after = await api.get(f"/properties/{fixed_upin}/ledger", OFFICER)
            assert any(e["txnType"] == "ADJUSTMENT" and e["amount"] == -50 and e["referenceNo"] == bill["demandNo"] for e in ledger_after), ledger_after[-3:]
            assert (await api.get(f"/properties/{fixed_upin}/dues", OFFICER))["advanceHeld"] == adv_before + 50
            assert next(d for d in await api.get(f"/properties/{fixed_upin}/demands", OFFICER) if d["demandNo"] == bill["demandNo"])["revised"] == -50
            raised = await api.post(f"/demands/{bill['demandNo']}/corrections", {"amount": 30, "reason": "Raised again after recheck"}, OFFICER)
            await api.post(f"/approvals/{raised['approvalId']}/decide", {"decision": "REJECT", "remark": "Not justified"}, COMMISSIONER)
            assert next(d for d in await api.get(f"/properties/{fixed_upin}/demands", OFFICER) if d["demandNo"] == bill["demandNo"])["revised"] == -50

            # ---- revision petition and appeal after the assessment is final (PT-24) ----
            case_view = await api.get(f"/cases/{re['applicationNo']}", OFFICER)
            assert case_view["petitionOptions"]["canFile"] == "REVISION_PETITION" and case_view["petitions"] == []
            grounds = "The setback was measured from the wrong boundary; it is 10 ft as per the approved plan."
            await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "APPEAL", "grounds": grounds}, OFFICER, expect=400)           # not yet
            await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "REVISION_PETITION", "grounds": "too short"}, OFFICER, expect=422)
            await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "REVISION_PETITION", "grounds": grounds, "mobileNumber": "9999999999"}, CITIZEN, expect=404)
            pet = await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "REVISION_PETITION", "grounds": grounds, "mobileNumber": "9100000302"}, CITIZEN)
            await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "REVISION_PETITION", "grounds": grounds}, OFFICER, expect=400)   # one at a time
            await api.post(f"/petitions/{pet['petitionNo']}/decide", {"outcome": "REJECT", "remark": "Measured twice"}, OFFICER, expect=403)    # Commissioner only
            await api.post(f"/petitions/{pet['petitionNo']}/decide", {"outcome": "ALLOW", "remark": "Allowed"}, COMMISSIONER, expect=400)       # needs the corrected details
            await api.post(f"/petitions/{pet['petitionNo']}/decide", {"outcome": "REJECT", "remark": "Measured twice on site"}, COMMISSIONER)
            assert (await api.get(f"/cases/{re['applicationNo']}", OFFICER))["petitionOptions"]["canFile"] == "APPEAL"
            appeal = await api.post(f"/cases/{re['applicationNo']}/petitions", {"level": "APPEAL", "grounds": grounds}, OFFICER)
            await api.post(f"/petitions/{appeal['petitionNo']}/decide", {"outcome": "ALLOW", "remark": "Order received", "property": {"measuredSetbackFt": 10}},
                           COMMISSIONER, expect=400)                                                                                         # needs the order number
            decided = await api.post(f"/petitions/{appeal['petitionNo']}/decide", {"outcome": "ALLOW", "remark": "Appellate order received",
                                                                                   "orderReference": "AA/2026/114", "property": {"measuredSetbackFt": 10}}, COMMISSIONER)
            assert decided["status"] == "ALLOWED" and decided["assessmentNo"]
            corrected = await api.get(f"/properties/{pen}", OFFICER)
            assert corrected["measuredSetbackFt"] == 10 and "SETBACK_PENALTY" not in corrected["assessment"]["components"], corrected["assessment"]
            assert corrected["assessment"]["kind"] == "APPEAL" and corrected["assessment"]["assessmentNo"] == decided["assessmentNo"]
            final_view = await api.get(f"/cases/{re['applicationNo']}", OFFICER)
            assert [x["status"] for x in final_view["petitions"]] == ["REJECTED", "ALLOWED"] and final_view["petitionOptions"]["canFile"] is None
            assert (await api.get("/petitions", COMMISSIONER, status="ALLOWED"))["total"] >= 1

            # ---- certificates: tax paid, assessment extract and NOC (PT-28) ----
            tax_paid = await api.post("/citizen/certificates", {"upin": paid_upin, "certType": "TAX_PAID"}, OFFICER)
            assert tax_paid["certType"] == "TAX_PAID" and tax_paid["content"]["receipts"] and tax_paid["content"]["balanceDue"] == 0, tax_paid
            ext_upin = await upin_of(api, "OLD-22-1018")
            extract = await api.post("/citizen/certificates", {"upin": ext_upin, "certType": "ASSESSMENT_EXTRACT"}, OFFICER)
            ext_assessment = (await api.get(f"/properties/{ext_upin}", OFFICER))["assessment"]
            assert extract["content"]["annualTax"] == ext_assessment["annualTax"] and extract["content"]["floors"], extract
            await api.post("/citizen/certificates", {"upin": paid_upin, "certType": "NOC"}, OFFICER, expect=400)                 # needs a purpose
            await api.post("/citizen/certificates", {"upin": due_prop, "certType": "NOC", "purpose": "Sale of the property"}, OFFICER, expect=400)  # dues
            hold = await api.post("/cases", {"appType": "REASSESSMENT", "upin": paid_upin, "consent": True, "reason": "Area to be rechecked",
                                             "property": {"siteAreaSqyd": 260}}, OFFICER)
            blocked = await client.post(f"{P}/citizen/certificates", headers=api.h(OFFICER), json={"upin": paid_upin, "certType": "NOC", "purpose": "Sale of the property"})
            assert blocked.status_code == 400 and "in progress" in blocked.text, blocked.text
            await api.post(f"/cases/{hold['applicationNo']}/actions", {"action": "REJECT", "remark": "Withdrawn by the owner"}, OFFICER)
            noc = await api.post("/citizen/certificates", {"upin": paid_upin, "certType": "NOC", "purpose": "Sale of the property"}, OFFICER)
            assert noc["certType"] == "NOC" and noc["purpose"] == "Sale of the property" and noc["content"]["duesCleared"] is True
            assert (datetime.date.fromisoformat(noc["validUntil"]) - now_d).days == 30
            genuine = await client.get("/api/v1/ptx/public/verify", params={"type": "CERTIFICATE", "no": noc["certificateNo"], "code": noc["verificationCode"], "tenant": "GWMC"})
            assert genuine.json()["genuine"] is True and genuine.json()["certType"] == "NOC"
            owner_extract = await api.post("/citizen/certificates", {"upin": paid_upin, "certType": "ASSESSMENT_EXTRACT", "mobileNumber": "9100000101"}, CITIZEN)
            assert owner_extract["certType"] == "ASSESSMENT_EXTRACT"
            await api.post("/citizen/certificates", {"upin": paid_upin, "certType": "ASSESSMENT_EXTRACT", "mobileNumber": "9999999999"}, CITIZEN, expect=404)

            # ---- complaints with time limits (PT-29) ----
            seeded = await api.get("/complaints", OFFICER, status="IN_PROGRESS")
            assert seeded["total"] >= 1 and seeded["items"][0]["category"] == "BILL_NOT_RECEIVED"
            await api.post("/complaints", {"upin": seeded["items"][0]["upin"], "category": "BILL_NOT_RECEIVED", "description": "Still no bill received here"}, OFFICER, expect=409)
            comp_body = {"upin": paid_upin, "category": "WRONG_AREA", "description": "The area recorded is more than what we have built.", "mobileNumber": "9100000101"}
            await api.post("/complaints", {**comp_body, "category": "MADE_UP"}, CITIZEN, expect=400)
            await api.post("/complaints", {**comp_body, "description": "short"}, CITIZEN, expect=422)
            await api.post("/complaints", {**comp_body, "mobileNumber": "9999999999"}, CITIZEN, expect=404)
            comp = await api.post("/complaints", comp_body, CITIZEN)
            assert comp["status"] == "OPEN" and comp["channel"] == "PORTAL" and comp["hint"] and "hear back" in comp["statusText"]
            assert 235 <= (datetime.datetime.fromisoformat(comp["dueAt"]) - datetime.datetime.utcnow()).total_seconds() / 3600 <= 241   # 240 hours for this category
            await api.get(f"/citizen/complaints/{comp['complaintNo']}", CITIZEN, expect=404, mobile="9999999999")
            assert (await api.get(f"/citizen/complaints/{comp['complaintNo']}", CITIZEN, mobile="9100000101"))["filedBy"] == "Owner"
            await api.post(f"/complaints/{comp['complaintNo']}/actions", {"action": "START", "remark": "Looking into it"}, CASHIER, expect=403)
            await api.post(f"/complaints/{comp['complaintNo']}/actions", {"action": "START", "remark": "Looking into it"}, INSPECTOR)
            await api.post(f"/complaints/{comp['complaintNo']}/actions", {"action": "RESOLVE", "remark": "Measured again; the record is right."}, OFFICER, expect=400)  # outcome needed
            await api.post(f"/complaints/{comp['complaintNo']}/actions", {"action": "RESOLVE", "remark": "Measured again; the record is right.",
                                                                          "outcome": "NO_CHANGE_NEEDED"}, OFFICER)
            done_c = await api.get(f"/citizen/complaints/{comp['complaintNo']}", CITIZEN, mobile="9100000101")
            assert done_c["status"] == "RESOLVED" and "record is right" in done_c["statusText"] and [e["action"] for e in done_c["timeline"]] == ["FILED", "START", "RESOLVE"]
            await api.post(f"/complaints/{comp['complaintNo']}/actions", {"action": "REOPEN", "remark": "Owner disagrees"}, OFFICER)
            from app.db.session import AsyncSessionLocal
            from app.db.ptx_models import PtxComplaint
            async with AsyncSessionLocal() as sess:
                row = await sess.scalar(select(PtxComplaint).where(PtxComplaint.complaint_no == comp["complaintNo"]))
                row.due_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
                await sess.commit()
            jobs = await api.post("/jobs/daily", None, ADMIN)
            assert jobs["complaintEscalations"] >= 1, jobs
            late = await api.get(f"/complaints/{comp['complaintNo']}", OFFICER)
            assert late["overdue"] is True and late["escalationLevel"] == 1 and "ESCALATED" in [e["action"] for e in late["timeline"]]
            assert (await api.get("/complaints", OFFICER, overdue="true"))["total"] >= 1

            # ---- bills: print a batch, track delivery (PT-20) ----
            cur = me["currentPeriod"]
            summary = await api.get("/demands/delivery-summary", INSPECTOR, period=cur, wardId=ward14)
            assert summary["DELIVERED"] >= 2 and summary["NOT_DELIVERED"] == 1 and summary["total"] == sum(summary[k] for k in ("PENDING", "DELIVERED", "NOT_DELIVERED"))
            batch = await api.get("/demands/batch", OFFICER, period=cur, wardId=ward14, limit=3)
            assert len(batch["items"]) == 3 and batch["total"] == summary["total"] and all(b["verifyPath"] and "dues" in b for b in batch["items"])
            sheet14 = await api.get("/field/sheet", INSPECTOR, wardId=ward14)
            assert sheet14["billsToDeliver"] and len(sheet14["billsToDeliver"]) == summary["PENDING"], (len(sheet14["billsToDeliver"]), summary)
            first_bill = sheet14["billsToDeliver"][0]["demandNo"]
            handed = await api.post("/demands/delivery", {"items": [{"demandNo": first_bill, "delivered": True, "latitude": 17.98, "longitude": 79.59}]}, INSPECTOR)
            assert handed["recorded"] == 1
            again = await api.post("/demands/delivery", {"items": [{"demandNo": first_bill, "delivered": True}]}, INSPECTOR)
            assert again["results"][0]["result"] == "ALREADY_RECORDED"
            no_note = await api.post("/demands/delivery", {"items": [{"demandNo": sheet14["billsToDeliver"][1]["demandNo"], "delivered": False}]}, INSPECTOR)
            assert no_note["errors"] == 1
            other_ward = (await api.get("/demands", OFFICER, period=cur, wardId=wards[22]["wardId"], limit=1))["items"][0]["demandNo"]
            outside = await api.post("/demands/delivery", {"items": [{"demandNo": other_ward, "delivered": True}]}, INSPECTOR)
            assert "outside your assigned area" in outside["results"][0]["error"]
            after = await api.get("/demands/delivery-summary", INSPECTOR, period=cur, wardId=ward14)
            assert after["DELIVERED"] == summary["DELIVERED"] + 1 and after["PENDING"] == summary["PENDING"] - 1
            not_delivered = await api.get("/demands", OFFICER, period=cur, delivery="NOT_DELIVERED")
            assert not_delivered["total"] >= 1 and not_delivered["items"][0]["deliveryNote"]

            # ---- remittance: verified closings are banked once and confirmed by another officer (PT-23) ----
            pend = await api.get("/remittances/pending-closes", CASHIER)
            assert len(pend["items"]) >= 2
            ids = [c["id"] for c in pend["items"]]
            bank = {"closeIds": ids, "bankName": "State Bank of India, Hanamkonda", "challanNo": "CH-2026-0001", "depositDate": now_d.isoformat(),
                    "depositedCash": pend["totalCash"], "depositedInstruments": pend["totalInstruments"]}
            await api.post("/remittances", bank, OFFICER, expect=403)                                                            # the cashier banks it
            await api.post("/remittances", {**bank, "closeIds": ["no-such-closing"]}, CASHIER, expect=404)
            await api.post("/remittances", {**bank, "depositedCash": pend["totalCash"] - 10}, CASHIER, expect=400)              # a difference needs a reason
            rem = await api.post("/remittances", bank, CASHIER)
            assert rem["status"] == "SUBMITTED" and rem["depositVariance"] == 0 and rem["expectedCash"] == pend["totalCash"], rem
            assert (await api.get("/remittances/pending-closes", CASHIER))["items"] == []
            await api.post("/remittances", bank, CASHIER, expect=409)                                                            # never banked twice
            await api.post(f"/remittances/{rem['remittanceNo']}/confirm", {"creditDate": now_d.isoformat(), "creditedAmount": rem["depositedTotal"]}, CASHIER, expect=403)
            early = (now_d - datetime.timedelta(days=2)).isoformat()
            await api.post(f"/remittances/{rem['remittanceNo']}/confirm", {"creditDate": early, "creditedAmount": rem["depositedTotal"]}, OFFICER, expect=400)
            await api.post(f"/remittances/{rem['remittanceNo']}/confirm", {"creditDate": now_d.isoformat(), "creditedAmount": rem["depositedTotal"] + 5}, OFFICER, expect=400)
            ok = await api.post(f"/remittances/{rem['remittanceNo']}/confirm", {"creditDate": now_d.isoformat(), "creditedAmount": rem["depositedTotal"]}, OFFICER)
            assert ok["status"] == "CONFIRMED" and ok["confirmedBy"] == OFFICER[0]
            await api.post(f"/remittances/{rem['remittanceNo']}/confirm", {"creditDate": now_d.isoformat(), "creditedAmount": rem["depositedTotal"]}, OFFICER, expect=409)
            # a second banking whose credit differs from what was banked is flagged
            yday = (now_d - datetime.timedelta(days=1)).isoformat()
            y_close = await api.post("/day-close", {"closeDate": yday, "declaredCash": 0}, COLLECTOR)
            await api.post(f"/day-close/{y_close['id']}/verify", {"receivedCash": 0}, CASHIER)
            rem2 = await api.post("/remittances", {"closeIds": [y_close["id"]], "bankName": "SBI", "challanNo": "CH-2026-0002", "depositDate": now_d.isoformat(),
                                                   "depositedCash": 0, "depositedInstruments": 0}, CASHIER)
            flagged = await api.post(f"/remittances/{rem2['remittanceNo']}/confirm", {"creditDate": now_d.isoformat(), "creditedAmount": 5,
                                                                                   "remark": "Bank credited Rs 5 against a nil deposit; queried"}, OFFICER)
            assert flagged["status"] == "MISMATCH"
            assert (await api.get("/remittances", CASHIER, status="MISMATCH"))["total"] == 1

            # ---- link switches: nothing works while its link is off, and the change is on record (PT-IR-06) ----
            await api.post("/integration/links/BBPS/toggle", {"enabled": False, "reason": "Testing the switch"}, OFFICER, expect=403)
            await api.post("/integration/links/BBPS/toggle", {"enabled": False, "reason": "no"}, ADMIN, expect=422)
            await api.post("/integration/links/NO_SUCH/toggle", {"enabled": False, "reason": "Testing the switch"}, ADMIN, expect=404)
            await api.post("/integration/links/BBPS/toggle", {"enabled": False, "reason": "Testing the switch"}, ADMIN)
            off = await client.post(f"{P}/integration/bbps/fetch", headers=api.h(OFFICER), json={"requestId": "REQ-0000", "upin": paid_upin})
            assert off.status_code == 409 and "switched off" in off.text, off.text
            assert find(await api.get("/integration/links", OFFICER), link="BBPS")["enabled"] is False
            await api.post("/integration/links/BBPS/toggle", {"enabled": True, "reason": "Testing is over"}, ADMIN)
            assert find(await api.get("/integration/links", OFFICER), link="BBPS")["enabled"] is True

            # ---- registered deeds start a change of owner (PT-14) ----
            assert (await api.get("/integration/registration/deeds", OFFICER, status="TO_REVIEW"))["total"] >= 1                 # the seeded deed whose seller does not match
            srinu = await upin_of(api, "OLD-48-1013")
            deed = {"deedNo": "DOC-1/2026", "registrationOffice": "Sub-Registrar, Kazipet", "deedDate": (now_d - datetime.timedelta(days=3)).isoformat(), "deedType": "sale",
                    "upin": srinu, "sellers": ["Srinu J"], "buyers": [{"fullName": "M. Latha", "mobileNumber": "9100000811"}], "considerationAmount": 900000}
            await api.post("/integration/registration/deeds", {"deeds": [deed]}, CASHIER, expect=403)
            got = await api.post("/integration/registration/deeds", {"deeds": [deed, {**deed, "deedNo": "DOC-2/2026", "deedDate": (now_d + datetime.timedelta(days=2)).isoformat()}]}, OFFICER)
            assert got["received"] == 1 and got["errors"] == 1 and got["results"][0]["status"] == "CASE_OPENED", got
            reg_case = await api.get(f"/cases/{got['results'][0]['applicationNo']}", OFFICER)
            assert reg_case["appType"] == "MUTATION" and reg_case["channel"] == "REGISTRATION" and reg_case["details"]["transfer"]["reason"] == "SALE"
            assert reg_case["details"]["owners"][0]["fullName"] == "M. Latha" and "DOC-1/2026" in reg_case["details"]["transfer"]["deedNo"]
            again_deed = await api.post("/integration/registration/deeds", {"deeds": [deed]}, OFFICER)
            assert again_deed["duplicates"] == 1 and again_deed["results"][0]["applicationNo"] == reg_case["applicationNo"]
            await advance(api, reg_case["applicationNo"], OFFICER, "Deed copy checked against the registry feed")
            fee_quote = await api.get(f"/properties/{srinu}/payable", CASHIER)
            await api.post("/payments", {"upin": srinu, "amount": fee_quote["payToClearAll"], "paymentMode": "CASH", "idempotencyKey": key()}, CASHIER)
            assert (await advance(api, reg_case["applicationNo"], OFFICER, "Fee and dues paid; approved"))["status"] == "COMPLETED"
            assert (await api.get(f"/properties/{srinu}", OFFICER))["owners"][0]["fullName"] == "M. Latha"
            # a seller who is not the owner on record, an unfamiliar kind of deed, a property already in a case, an unknown property
            mallaiah = await upin_of(api, "OLD-48-1019")
            mismatch = await api.post("/integration/registration/deeds", {"deeds": [{**deed, "deedNo": "DOC-3/2026", "upin": mallaiah, "sellers": ["Totally Different"]}]}, OFFICER)
            assert mismatch["results"][0]["status"] == "REVIEW" and "do not match" in mismatch["results"][0]["message"]
            lease = await api.post("/integration/registration/deeds", {"deeds": [{**deed, "deedNo": "DOC-4/2026", "upin": await upin_of(api, "OLD-22-1006"), "sellers": ["R. Yadagiri"],
                                                                                    "deedType": "lease"}]}, OFFICER)
            assert lease["results"][0]["status"] == "REVIEW" and "not a kind of transfer" in lease["results"][0]["message"]
            nomatch = await api.post("/integration/registration/deeds", {"deeds": [{**deed, "deedNo": "DOC-5/2026", "upin": "GWMC-P-99999999"}]}, OFFICER)
            assert nomatch["results"][0]["status"] == "NO_MATCH"
            listed = await api.get("/integration/registration/deeds", OFFICER, status="TO_REVIEW", limit=20)
            by_no = {d["deedNo"]: d for d in listed["items"]}
            await api.post(f"/integration/registration/deeds/{by_no['DOC-5/2026']['id']}/open-case", {"remark": "Checked the deed"}, OFFICER, expect=400)   # no property chosen
            await api.post(f"/integration/registration/deeds/{by_no['DOC-5/2026']['id']}/dismiss", {"remark": "Deed is for land outside the city"}, OFFICER)
            await api.post(f"/integration/registration/deeds/{by_no['DOC-5/2026']['id']}/dismiss", {"remark": "Again"}, OFFICER, expect=409)
            opened = await api.post(f"/integration/registration/deeds/{by_no['DOC-3/2026']['id']}/open-case", {"remark": "Seller is the owner's late husband; deed checked"}, OFFICER)
            assert opened["applicationNo"]
            await api.post(f"/integration/registration/deeds/{by_no['DOC-3/2026']['id']}/open-case", {"remark": "Again"}, OFFICER, expect=409)
            busy = await api.post("/integration/registration/deeds", {"deeds": [{**deed, "deedNo": "DOC-6/2026", "upin": mallaiah, "sellers": ["G. Mallaiah"]}]}, OFFICER)
            assert busy["results"][0]["status"] == "REVIEW" and "in progress" in busy["results"][0]["message"], busy

            # ---- state platform sync (PT-02) ----
            sync_a, sync_b = await upin_of(api, "OLD-14-1000"), await upin_of(api, "OLD-14-1002")
            export = await api.get("/integration/state/export", OFFICER, limit=5)
            assert export["format"] == "urban.ptx.state-sync.v1" and len(export["records"]) == 5 and "mobile" not in str(export).lower()
            imported = await api.post("/integration/state/import", {"records": [
                {"stateRef": "STATE-TG-0001", "upin": sync_a, "pincode": "506001", "address": "H.No 2-4-123/A, Postal Colony, Subedari, Hanamkonda"},
                {"stateRef": "STATE-TG-0002", "oldAssessmentNo": "NOPE-1"},
                {"stateRef": "STATE-TG-0003", "upin": sync_b, "latitude": 17.98},
                {"stateRef": "STATE-TG-0001", "upin": sync_b}]}, OFFICER)
            assert (imported["records"], imported["matched"], imported["updated"], imported["unmatched"], imported["errors"]) == (4, 3, 1, 1, 2), imported
            assert "already belongs to" in imported["results"][3].get("error", "") and imported["results"][1]["result"] == "UNMATCHED"
            synced = await api.get(f"/properties/{sync_a}", OFFICER)
            assert synced["stateRef"] == "STATE-TG-0001" and synced["pincode"] == "506001"
            assert any("State platform sync" in (h["reason"] or "") for h in await api.get(f"/properties/{sync_a}/history", OFFICER))
            repeat = await api.post("/integration/state/import", {"records": [{"stateRef": "STATE-TG-0001", "upin": sync_a, "pincode": "506001"}]}, OFFICER)
            assert repeat["updated"] == 0 and repeat["results"][0]["result"] == "UNCHANGED"
            assert (await api.get("/integration/state/runs", OFFICER))["total"] >= 3

            # ---- BBPS: fetch what is due, pay it, never twice (PT-21) ----
            owing = (await api.get("/properties", OFFICER, paymentStatus="ARREARS", limit=5))["items"][0]["upin"]
            unknown = await api.post("/integration/bbps/fetch", {"requestId": "REQ-0001", "upin": "GWMC-P-99999999"}, OFFICER)
            assert unknown["status"] == "BILL_NOT_FOUND"
            assert (await api.post("/integration/bbps/fetch", {"requestId": "REQ-0002", "upin": paid_upin}, OFFICER))["status"] == "NO_DUES"
            bill = await api.post("/integration/bbps/fetch", {"requestId": "REQ-0003", "upin": owing}, OFFICER)
            owed = (await api.get(f"/properties/{owing}/dues", OFFICER))["netPayable"]
            assert bill["status"] == "OK" and bill["billerResponse"]["amount"] == owed and "*" in bill["billerResponse"]["customerName"], bill
            await api.post("/integration/bbps/pay", {"requestId": "REQ-0004", "upin": owing, "amount": owed + 1, "bbpsTxnRef": "BBPS-TXN-0001"}, OFFICER)
            over = await api.post("/integration/bbps/pay", {"requestId": "REQ-0004", "upin": owing, "amount": owed + 1, "bbpsTxnRef": "BBPS-TXN-0001"}, OFFICER)
            assert over["status"] == "AMOUNT_EXCEEDS_DUE", over
            paid_bbps = await api.post("/integration/bbps/pay", {"requestId": "REQ-0005", "upin": owing, "amount": 100, "bbpsTxnRef": "BBPS-TXN-0001"}, OFFICER)
            assert paid_bbps["status"] == "PAID" and paid_bbps["duplicate"] is False
            dup = await api.post("/integration/bbps/pay", {"requestId": "REQ-0006", "upin": owing, "amount": 100, "bbpsTxnRef": "BBPS-TXN-0001"}, OFFICER)
            assert dup["duplicate"] is True and dup["receiptNo"] == paid_bbps["receiptNo"]
            await api.post("/integration/bbps/pay", {"requestId": "REQ-0007", "upin": owing, "amount": 90, "bbpsTxnRef": "BBPS-TXN-0001"}, OFFICER, expect=400)
            assert (await api.get(f"/properties/{owing}/dues", OFFICER))["netPayable"] == round(owed - 100, 2)
            assert (await api.get("/integration/bbps/status/BBPS-TXN-0001", OFFICER))["status"] == "PAID"
            assert (await api.get("/integration/bbps/status/NOPE-0000", OFFICER))["status"] == "NOT_FOUND"
            statement = await api.get("/reconciliation/stand-in-statement", CASHIER, date=now_d.isoformat())
            assert any(r["reference"] == "BBPS-TXN-0001" and r["amount"] == 100 for r in statement), statement
            recon_today = await api.post("/reconciliation", {"statementDate": now_d.isoformat(), "source": "GATEWAY", "rows": statement}, CASHIER)
            assert not any(m.get("reference") == "BBPS-TXN-0001" for m in recon_today["mismatches"]), recon_today["mismatches"]

            # ---- card machine (POS) payments need the approval code (PT-21) ----
            pos_body = {"upin": owing, "amount": 50, "paymentMode": "POS", "idempotencyKey": key()}
            await api.post("/payments", pos_body, CASHIER, expect=400)
            pos = await api.post("/payments", {**pos_body, "instrumentNo": "RRN-4471920", "idempotencyKey": key()}, CASHIER)
            assert pos["paymentMode"] == "POS" and pos["instrumentNo"] == "RRN-4471920"

            # daily job runs cleanly twice
            await api.post("/jobs/daily", None, ADMIN)
            await api.post("/jobs/daily", None, ADMIN)


def test_property_tax_end_to_end():
    asyncio.run(scenario())
