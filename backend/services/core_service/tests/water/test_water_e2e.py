"""
End-to-end test of Module 2 (Water & Utility Billing) against a fresh SQLite database.

Run from backend/services/core_service:
    pip install -r requirements.txt -r requirements-dev.txt
    python -m pytest tests/water -q

The app is started in-process (lifespan runs the core and water seeds), then every SRS workflow is driven
through the HTTP API with real sign-ins for each water role.
"""
import asyncio
import base64
import datetime
import os
import tempfile
import uuid
from decimal import Decimal

_TMP = tempfile.mkdtemp(prefix="wtr-e2e-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/water.db"
os.environ["WATER_STORAGE_DIR"] = os.path.join(_TMP, "storage")
os.environ["ENVIRONMENT"] = "development"

import httpx  # noqa: E402

from app.main import app  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
W = "/api/v1/water"


class Api:
    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.tokens = {}

    async def login(self, user: str, password: str = "Water@123") -> None:
        r = await self.c.post("/api/v1/auth/signin", json={"userName": user, "password": password})
        assert r.status_code == 200, r.text
        self.tokens[user] = r.json()["accessToken"]

    def h(self, user=None):
        headers = {"X-Tenant-ID": "GWMC"}
        if user:
            headers["Authorization"] = f"Bearer {self.tokens[user]}"
        return headers

    async def get(self, path, user=None, expect=200, **params):
        r = await self.c.get(W + path, headers=self.h(user), params=params)
        assert r.status_code == expect, f"GET {path} -> {r.status_code}: {r.text}"
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    async def post(self, path, body=None, user=None, expect=(200, 201), **params):
        r = await self.c.post(W + path, headers=self.h(user), json=body, params=params)
        expected = expect if isinstance(expect, tuple) else (expect,)
        assert r.status_code in expected, f"POST {path} -> {r.status_code}: {r.text}"
        return r.json()

    async def patch(self, path, body, user=None, expect=200):
        r = await self.c.patch(W + path, headers=self.h(user), json=body)
        assert r.status_code == expect, f"PATCH {path} -> {r.status_code}: {r.text}"
        return r.json()


OFFICER = "water.officer@gwmc.gov.in"
READER = "meter.reader@gwmc.gov.in"
FIELD = "water.fieldstaff@gwmc.gov.in"
CASHIER = "cashier@gwmc.gov.in"
COMMISSIONER = "commissioner@gwmc.gov.in"
CSC = "csc.operator@gwmc.gov.in"


def key():
    return uuid.uuid4().hex


async def scenario():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
            api = Api(client)
            for user in (OFFICER, READER, FIELD, CASHIER, COMMISSIONER, CSC):
                await api.login(user)

            # ---- seed sanity and bill arithmetic (WB-20, WB-24) -------------------------------------
            bills = await api.get("/connections/GWMC-W-0000001/bills", OFFICER)
            assert len(bills) == 4
            # domestic 15 mm, 7/kL up to 15 kL, 11/kL to 30 kL, minimum Rs 100, fixed Rs 30; history 14,15,13,16 kL
            assert [b["consumptionKl"] for b in bills] == [16.0, 13.0, 15.0, 14.0]
            assert [b["waterCharge"] for b in bills] == [116.0, 100.0, 105.0, 100.0]  # 15x7+1x11 / min 100 / 15x7 / min 100
            assert all(b["basis"] == "ACTUAL" and b["fixedCharge"] == 30.0 for b in bills)
            tiffin = await api.get("/connections/GWMC-W-0000004/bills", OFFICER)
            latest = tiffin[0]  # non-domestic 43 kL: 25 x 25 + 18 x 35 = 1255, fixed 100, cess 2% = 25.10
            assert latest["consumptionKl"] == 43.0 and latest["waterCharge"] == 1255.0
            assert latest["cess"] == 25.1 and latest["currentDemand"] == 1380.1
            avg_bill = (await api.get("/connections/GWMC-W-0000014/bills", OFFICER))[0]
            assert avg_bill["basis"] == "AVERAGE" and avg_bill["consumptionKl"] == 12.333  # door locked (WB-14, WB-16)
            flat = (await api.get("/connections/GWMC-W-0000005/bills", OFFICER))[0]
            assert flat["basis"] == "FLAT" and flat["waterCharge"] == 150.0  # non-metered 15 mm (WB-17)

            # ---- ward scope (WB-NF-10): the reader is limited to ward 14 ----------------------------
            mine = await api.get("/connections", READER, limit=200)
            assert mine and {c["wardNumber"] for c in mine} == {14}
            await api.get("/connections/GWMC-W-0000006", READER, expect=403)
            await api.post("/billing/run", {"cycle": "2026-10"}, user=READER, expect=403)

            # ---- a super admin's live permission override reaches real enforcement here too (PT-NF-10) ----
            # (Phase 2 of the Roles & Permission Matrix redesign - same shared mechanism proven in tests/ptx,
            # this just checks the Water side wires up correctly too; no write endpoint yet, so poke directly)
            from app.db.session import AsyncSessionLocal
            from app.db.models import PermissionOverride
            from app.core.permission_overrides import invalidate_overrides

            async def set_override(role: str, granted, effective_from) -> None:
                async with AsyncSessionLocal() as sess:
                    sess.add(PermissionOverride(tenant_id="GWMC", module_code="WTR", permission_key="reports.view",
                                                role=role, granted=granted, created_by="test", effective_from=effective_from))
                    await sess.commit()
                await invalidate_overrides("GWMC", "WTR")

            today = datetime.date.today()
            await api.get("/arrears/ageing", FIELD, expect=403)  # baseline: field staff have neither permission that guards this
            await set_override("water_field_staff", True, today)
            await api.get("/arrears/ageing", FIELD)
            await api.get("/arrears/ageing", READER, expect=403)  # the override is per-role: meter reader is untouched
            await set_override("water_field_staff", None, today)  # tombstone: reverts to the hardcoded default
            await api.get("/arrears/ageing", FIELD, expect=403)

            # ---- new connection workflow (WB-04, WB-05) -------------------------------------------
            wards = (await api.get("/me", OFFICER))["wards"]
            ward35 = next(w for w in wards if w["wardNumber"] == 35)
            dup = await api.post("/connections/duplicate-check", {"address": "H.No 1-12-88, Green Meadows Avenue, Nakkalagutta",
                                                                  "latitude": 17.9956, "longitude": 79.5885}, user=OFFICER)
            assert dup, "expected a duplicate warning near an existing connection"
            app_ = await api.post("/applications", {
                "appType": "NEW_CONNECTION", "channel": "CSC", "applicantName": "Test Applicant", "mobileNumber": "9876543210",
                "aadhaarNumber": "234567890123", "consent": True, "wardId": ward35["wardId"], "address": "H.No 9-9-9, Test Street",
                "doorNo": "9-9-9", "latitude": 17.9990, "longitude": 79.5800, "categoryCode": "DOMESTIC", "pipeSizeMm": 15,
                "isMetered": True}, user=CSC)
            no = app_["applicationNo"]
            assert app_["aadhaarMasked"] == "XXXX-XXXX-0123" and app_["currentStep"] == "DOC_CHECK"
            assert next(s for s in app_["steps"] if s["code"] == "PTAX_DUES_CHECK")["status"] == "SKIPPED"  # WB-IR-06
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "docs ok"}, user=FIELD, expect=400)
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "Documents verified"}, user=OFFICER)
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "Line 6 m away",
                                                          "data": {"roadCuttingMetres": 2}}, user=FIELD)
            detail = await api.get(f"/applications/{no}", OFFICER)
            assert detail["estimateTotal"] == 3000 + 2 * 1200 + 2000 and detail["amountOutstanding"] == 7400.0
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "paid?"}, user=OFFICER, expect=400)
            await api.post("/payments", {"applicationNo": no, "amount": 7000, "paymentMode": "CASH", "idempotencyKey": key()},
                           user=CASHIER, expect=400)  # must be paid in full
            await api.post("/payments", {"applicationNo": no, "amount": 7400, "paymentMode": "CASH", "idempotencyKey": key()}, user=CASHIER)
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "Paid"}, user=OFFICER)
            await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "Laid", "data": {"meter": {
                "serialNo": "TEST-MTR-1", "make": "Itron", "sizeMm": 15, "fixedOn": str(datetime.date.today()), "initialReading": 0}}}, user=FIELD)
            done = await api.post(f"/applications/{no}/actions", {"action": "COMPLETE_STEP", "remark": "Activated"}, user=OFFICER)
            assert done["status"] == "COMPLETED" and done["consumerNo"]
            new_no = done["consumerNo"]
            conn = await api.get(f"/connections/{new_no}", OFFICER)
            assert conn["dues"]["depositHeld"] == 2000.0 and conn["meter"]["serialNo"] == "TEST-MTR-1"
            assert conn["aadhaarMasked"] == "XXXX-XXXX-0123"

            # ---- connection correction and history (WB-08) ----------------------------------------
            await api.patch(f"/connections/{new_no}", {"reason": "Applicant gave UPIN", "upin": "TG-GWMC-999"}, user=OFFICER)
            hist = await api.get(f"/connections/{new_no}/history", OFFICER)
            assert any(h["field"] == "upin" and h["newValue"] == "TG-GWMC-999" and h["changedBy"] == OFFICER for h in hist)
            assert (await api.get(f"/connections/{new_no}", OFFICER))["upinSource"] == "STAFF"

            # ---- reading intake: photo/GPS rule, idempotency, lower-than-last (WB-13..WB-19) ---------
            ref = key()
            bad = await api.post("/readings/intake", {"source": "FIELD", "readings": [
                {"consumerNo": new_no, "readingValue": 5, "clientRef": key()}]}, user=OFFICER)
            assert bad["errors"] == 1 and "photo" in bad["results"][0]["error"].lower()
            batch = {"source": "BULK", "readings": [
                {"consumerNo": new_no, "readingValue": 12, "clientRef": ref},
                {"consumerNo": "GWMC-W-0000005", "readingValue": 3, "clientRef": key()},  # non-metered -> row error only
            ]}
            first = await api.post("/readings/intake", batch, user=OFFICER)
            assert first["stored"] == 1 and first["errors"] == 1
            again = await api.post("/readings/intake", batch, user=OFFICER)
            assert again["duplicates"] == 1 and again["stored"] == 0
            low = await api.post("/readings/intake", {"source": "OFFICE", "readings": [
                {"consumerNo": "GWMC-W-0000002", "readingValue": 1.0, "clientRef": key()}]}, user=OFFICER)
            assert low["results"][0]["flag"] == "LOWER_THAN_LAST"
            pending = await api.get("/readings", OFFICER, status="PENDING_REVIEW")
            low_id = next(r["id"] for r in pending if r["consumerNo"] == "GWMC-W-0000002")
            await api.post(f"/readings/{low_id}/review", {"decision": "ACCEPT", "remark": "Looks fine"}, user=OFFICER, expect=400)
            await api.post(f"/readings/{low_id}/review", {"decision": "REJECT", "remark": "Misread"}, user=OFFICER)

            # ---- bill run: held flagged reading, resumable, no double billing (WB-23, WB-NF-63) ------
            cycle = (await api.get("/cycles/current", OFFICER))["cycle"]
            run1 = await api.post("/billing/run", {"cycle": cycle}, user=OFFICER)
            held = {h["consumerNo"] for h in run1["held"]}
            assert "GWMC-W-0000001" in held  # high reading waiting for review
            assert run1["billsRaised"] > 0
            run2 = await api.post("/billing/run", {"cycle": cycle}, user=OFFICER)
            assert run2["billsRaised"] == 0  # nothing billed twice
            flagged = next(r for r in await api.get("/readings", OFFICER, status="PENDING_REVIEW") if r["consumerNo"] == "GWMC-W-0000001")
            await api.post(f"/readings/{flagged['id']}/review", {"decision": "ACCEPT", "remark": "Verified leak inside premises"}, user=OFFICER)
            run3 = await api.post("/billing/run", {"cycle": cycle}, user=OFFICER)
            assert run3["billsRaised"] >= 1 and "GWMC-W-0000001" not in {h["consumerNo"] for h in run3["held"]}
            rejected_bill = next(b for b in await api.get("/connections/GWMC-W-0000002/bills", OFFICER) if b["cycle"] == cycle)
            assert rejected_bill["basis"] == "AVERAGE"  # rejected reading -> average billing

            # ---- payments: allocation order, advance, idempotency (WB-31, WB-32, WB-NF-32) ---------
            dues = await api.get("/connections/GWMC-W-0000013/dues", CASHIER)  # never-paying hotel: penalty + arrears + current
            assert dues["penalty"] > 0 and dues["arrears"] > 0 and dues["current"] > 0
            k = key()
            part = await api.post("/payments", {"consumerNo": "GWMC-W-0000013", "amount": dues["penalty"] + 100,
                                                "paymentMode": "CASH", "idempotencyKey": k}, user=CASHIER)
            assert part["allocation"]["PENALTY"] == dues["penalty"] and part["allocation"]["ARREAR"] == 100.0
            same = await api.post("/payments", {"consumerNo": "GWMC-W-0000013", "amount": dues["penalty"] + 100,
                                                "paymentMode": "CASH", "idempotencyKey": k}, user=CASHIER)
            assert same["receiptNo"] == part["receiptNo"]
            d1 = await api.get("/connections/GWMC-W-0000001/dues", CASHIER)
            over = await api.post("/payments", {"consumerNo": "GWMC-W-0000001", "amount": d1["totalDue"] + 50,
                                                "paymentMode": "UPI", "idempotencyKey": key()}, user=CASHIER)
            assert over["allocation"]["ADVANCE"] == 50.0
            assert (await api.get("/connections/GWMC-W-0000001/dues", CASHIER))["advanceHeld"] == 50.0

            # ---- online payment with lost confirmation, status check, reconciliation (WB-34, WB-35) ---
            due13 = (await api.get("/connections/GWMC-W-0000013/dues", CASHIER))["totalDue"]
            order = await api.post("/payments/online/initiate", {"consumerNo": "GWMC-W-0000013", "amount": 500})
            lost = await api.post("/payments/online/stub-gateway", {"orderId": order["orderId"], "outcome": "SUCCESS_NO_CALLBACK"})
            assert lost["callback"] == "LOST"
            assert (await api.get("/connections/GWMC-W-0000013/dues", CASHIER))["totalDue"] == due13
            check = await api.post("/payments/online/status-check", {})
            assert len(check["completed"]) == 1
            dup_cb = await api.post("/payments/online/callback", {"orderId": order["orderId"], "status": "SUCCESS"})
            assert dup_cb["duplicate"] is True
            assert round((await api.get("/connections/GWMC-W-0000013/dues", CASHIER))["totalDue"], 2) == round(due13 - 500, 2)
            stmt = await api.get("/reconciliation/stand-in-statement", CASHIER, date=str(datetime.date.today()))
            rec = await api.post("/reconciliation", {"statementDate": str(datetime.date.today()), "rows": stmt + [
                {"reference": "UNKNOWN-TXN", "amount": 10}]}, user=CASHIER)
            assert rec["matched"] == 1 and any(m["type"] == "NOT_IN_SYSTEM" for m in rec["mismatches"])

            # ---- receipt cancellation through approval; maker cannot approve (WB-33) -----------------
            await api.post(f"/receipts/{part['receiptNo']}/cancel", {"reason": "Wrong consumer number entered"}, user=CASHIER)
            appr = next(a for a in await api.get("/approvals", OFFICER) if a["refNo"] == part["receiptNo"])
            await api.post(f"/approvals/{appr['id']}/decide", {"decision": "APPROVE", "remark": "Looks fine"}, user=CASHIER, expect=(400, 403))
            await api.post(f"/approvals/{appr['id']}/decide", {"decision": "APPROVE", "remark": "Verified with counter slip"}, user=OFFICER)
            assert (await api.get(f"/receipts/{part['receiptNo']}", CASHIER))["status"] == "CANCELLED"
            verify = await api.get("/public/verify", None, type="RECEIPT", no=part["receiptNo"], code=part["verificationCode"], tenant="GWMC")
            assert verify["genuine"] is True and verify["status"] == "CANCELLED" and "consumerName" not in verify
            fake = await api.get("/public/verify", None, type="RECEIPT", no=part["receiptNo"], code="BADCODE", tenant="GWMC")
            assert fake["genuine"] is False

            # ---- cheque return (WB-36) ----------------------------------------------------------
            before = (await api.get("/connections/GWMC-W-0000019/dues", CASHIER))["totalDue"]
            chq = await api.post("/payments", {"consumerNo": "GWMC-W-0000019", "amount": 200, "paymentMode": "CHEQUE",
                                               "instrumentNo": "123456", "instrumentBank": "SBI", "instrumentDate": str(datetime.date.today()),
                                               "idempotencyKey": key()}, user=CASHIER)
            await api.post(f"/receipts/{chq['receiptNo']}/cheque-return", {"reason": "Insufficient funds"}, user=CASHIER)
            after = (await api.get("/connections/GWMC-W-0000019/dues", CASHIER))
            assert round(after["totalDue"], 2) == round(before + 300, 2) and after["fees"] >= 300

            # ---- day-end closing (WB-37) --------------------------------------------------------
            close = await api.post("/day-close", {"closeDate": str(datetime.date.today()), "declaredCash": 1}, user=CASHIER)
            assert close["systemCash"] > 0
            await api.post(f"/day-close/{close['id']}/verify", {"receivedCash": 1}, user=CASHIER, expect=400)  # own closing
            verified = await api.post(f"/day-close/{close['id']}/verify", {"receivedCash": close["systemCash"]})
            assert verified["variance"] == 0.0

            # ---- waiver with approval limits (WB-46) ---------------------------------------------
            hotel = await api.get("/connections/GWMC-W-0000013/dues", OFFICER)
            await api.post("/connections/GWMC-W-0000013/waivers", {"kind": "WRITE_OFF", "bucket": "ARREAR",
                                                                    "amount": 10500, "reason": "Old disputed arrears"}, user=OFFICER)
            wo = next(a for a in await api.get("/approvals", COMMISSIONER) if a["approvalType"] == "WRITE_OFF")
            assert wo["canDecide"] is True
            await api.post(f"/approvals/{wo['id']}/decide", {"decision": "APPROVE", "remark": "Looks fine"}, user=OFFICER, expect=(400, 403))
            await api.post(f"/approvals/{wo['id']}/decide", {"decision": "APPROVE", "remark": "Approved as per council resolution"}, user=COMMISSIONER)
            assert round((await api.get("/connections/GWMC-W-0000013/dues", OFFICER))["arrears"], 2) == round(hotel["arrears"] - 10500, 2)

            # ---- bill correction is an adjustment, the bill never changes (WB-26) --------------------
            b = next(x for x in await api.get("/connections/GWMC-W-0000003/bills", OFFICER) if x["cycle"] == cycle)
            await api.post(f"/bills/{b['billNo']}/adjustments", {"amount": -20, "reason": "Reader typing error"}, user=OFFICER)
            adj = next(a for a in await api.get("/approvals", COMMISSIONER) if a["approvalType"] == "BILL_ADJUSTMENT")
            await api.post(f"/approvals/{adj['id']}/decide", {"decision": "APPROVE", "remark": "Checked"}, user=COMMISSIONER)
            b2 = await api.get(f"/bills/{b['billNo']}", OFFICER)
            assert b2["currentDemand"] == b["currentDemand"] and b2["approvedAdjustments"] == -20.0

            # ---- disconnection and reconnection (WB-43..WB-45) ------------------------------------
            orders = await api.get("/orders", FIELD, type="DISCONNECTION", status="PENDING")
            assert orders, "seed should leave connections listed for disconnection"
            target = orders[0]
            cut_no = target["consumerNo"]
            await api.post(f"/orders/{target['orderNo']}/execute", {"photoRef": "x.jpg", "latitude": 17.97, "longitude": 79.59,
                                                                   "remark": "Valve closed and sealed"}, user=FIELD)
            assert (await api.get(f"/connections/{cut_no}", OFFICER))["status"] == "DISCONNECTED"
            await api.post("/billing/run", {"cycle": cycle}, user=OFFICER)  # disconnected connections are not billed (WB-44)
            recon = await api.post(f"/connections/{cut_no}/reconnection", {}, user=OFFICER)
            assert recon["status"] == "AWAITING_PAYMENT" and recon["amountToPay"] > 0
            await api.post("/payments", {"consumerNo": cut_no, "amount": recon["amountToPay"], "paymentMode": "CASH",
                                         "idempotencyKey": key()}, user=CASHIER)
            ro = next(o for o in await api.get("/orders", FIELD, type="RECONNECTION") if o["orderNo"] == recon["orderNo"])
            assert ro["status"] == "PENDING" and ro["slaDueAt"]
            await api.post(f"/orders/{recon['orderNo']}/execute", {"photoRef": "y.jpg", "latitude": 17.97, "longitude": 79.59}, user=FIELD)
            assert (await api.get(f"/connections/{cut_no}", OFFICER))["status"] == "ACTIVE"

            # ---- complaints (WB-50, WB-51) -------------------------------------------------------
            cmp = await api.post("/complaints", {"complaintType": "LEAK", "source": "WHATSAPP", "wardId": ward35["wardId"],
                                                 "description": "Leak on road", "latitude": 17.99, "longitude": 79.58,
                                                 "complainantMobile": "9123456789"}, user=CSC)
            assert cmp["assignedTo"] == "water.fieldstaff@gwmc.gov.in"
            await api.post(f"/complaints/{cmp['complaintNo']}/actions", {"action": "CLOSE", "remark": "Fixed"}, user=FIELD, expect=400)
            await api.post(f"/complaints/{cmp['complaintNo']}/actions", {"action": "START", "remark": "On site"}, user=FIELD)
            closed = await api.post(f"/complaints/{cmp['complaintNo']}/actions",
                                    {"action": "CLOSE", "remark": "Joint replaced", "photoRef": "z.jpg"}, user=FIELD)
            assert closed["status"] == "CLOSED"

            # ---- illegal connection regularised (WB-53) --------------------------------------------
            case = next(c for c in await api.get("/illegal-cases", OFFICER) if c["status"] == "REPORTED")
            await api.post(f"/illegal-cases/{case['caseNo']}/inspection", {"findings": "Direct tap, no meter", "confirmedIllegal": True}, user=FIELD)
            reg = await api.post(f"/illegal-cases/{case['caseNo']}/decision", {"decision": "REGULARISE", "remark": "Owner agreed",
                                                                               "consumerName": "J. Ravi", "mobileNumber": "9000000999",
                                                                               "categoryCode": "DOMESTIC", "pipeSizeMm": 15,
                                                                               "isMetered": False}, user=OFFICER)
            assert reg["status"] == "REGULARISED"
            assert (await api.get(f"/connections/{reg['consumerNo']}/dues", OFFICER))["fees"] == 5000.0

            # ---- tariff change needs Commissioner approval (WB-21) -----------------------------------
            future = str(datetime.date.today() + datetime.timedelta(days=30))
            t = await api.post("/tariffs", {"categoryCode": "DOMESTIC", "effectiveFrom": future, "reason": "G.O. revision",
                                            "slabs": [{"uptoKl": 20, "ratePerKl": 8}, {"uptoKl": None, "ratePerKl": 22}],
                                            "flatRates": {"15": 160}, "minimumCharge": 110, "fixedCharge": 30}, user=OFFICER)
            assert t["status"] == "PENDING_APPROVAL"
            ta = next(a for a in await api.get("/approvals", COMMISSIONER) if a["approvalType"] == "TARIFF")
            await api.post(f"/approvals/{ta['id']}/decide", {"decision": "APPROVE", "remark": "Looks fine"}, user=OFFICER, expect=(400, 403))
            await api.post(f"/approvals/{ta['id']}/decide", {"decision": "APPROVE", "remark": "As per G.O."}, user=COMMISSIONER)
            tariffs = await api.get("/tariffs", OFFICER, category="DOMESTIC")
            assert {x["version"] for x in tariffs} == {1, 2} and next(x for x in tariffs if x["version"] == 1)["inForce"]

            # ---- settings are versioned, never back-dated (WB-NF-50) -------------------------------
            await api.post("/admin/settings", {"key": "penalty", "value": {"percent": 3, "graceDays": 0},
                                               "effectiveFrom": "2020-01-01", "reason": "test back-dating"}, expect=400)
            await api.post("/admin/settings", {"key": "penalty", "value": {"percent": 3, "graceDays": 0},
                                               "effectiveFrom": future, "reason": "Council resolution 12"})

            # ---- uploads, export, migration, citizen lookup, daily jobs ------------------------------
            up = await client.post(W + "/uploads", headers=api.h(FIELD), files={"file": ("m.png", PNG, "image/png")})
            assert up.status_code == 201, up.text
            got = await client.get(W + f"/uploads/{up.json()['ref']}", headers=api.h(FIELD))
            assert got.status_code == 200 and got.content == PNG
            csv_text = await api.get("/export/connections", OFFICER, format="csv")
            assert "consumerNo" in csv_text and "9000000101" not in csv_text  # no mobile numbers (WB-NF-23)
            mig = await api.post("/migration/connections", {"arrearsAsOf": "2026-03-31", "records": [
                {"oldConsumerNo": "OLD-X-1", "consumerName": "Migrated One", "address": "Somewhere", "wardNumber": 22,
                 "categoryCode": "DOMESTIC", "pipeSizeMm": 15, "isMetered": False, "openingArrears": 1234.5},
                {"oldConsumerNo": "OLD-X-2", "consumerName": "Bad Ward", "address": "Nowhere", "wardNumber": 999,
                 "categoryCode": "DOMESTIC", "pipeSizeMm": 15, "isMetered": False}]})
            assert len(mig["created"]) == 1 and len(mig["exceptions"]) == 1 and mig["locationPending"] == 1
            found = await api.get("/connections", OFFICER, q="OLD-X-1")
            assert found and found[0]["totalDue"] == 1234.5
            look = await api.get("/citizen/lookup", None, consumerNo="GWMC-W-0000002", mobile="9000000102")
            assert look["consumerNo"] == "GWMC-W-0000002"
            await api.get("/citizen/lookup", None, consumerNo="GWMC-W-0000002", mobile="9999999999", expect=404)
            jobs = await api.post("/jobs/daily", {}, user=OFFICER)
            assert "penalty" in jobs and "disconnection" in jobs

            # ---- reports stay consistent ----------------------------------------------------------
            dcb = await api.get("/reports/dcb", OFFICER)
            t_ = dcb["totals"]
            assert round(t_["opening"] + t_["demand"] - t_["collection"] + t_["adjustments"], 2) == t_["closing"]
            heads = await api.get("/reports/account-heads", OFFICER, day=str(datetime.date.today()))
            assert heads["rows"]
            events = (await api.get("/admin/events", COMMISSIONER))["counts"]
            for ev in ("connection.created", "meter.fixed", "bill.raised", "payment.received", "receipt.cancelled",
                       "connection.disconnected", "connection.reconnected", "complaint.raised", "complaint.closed",
                       "illegal_case.opened", "illegal_case.closed", "connection.changed"):
                assert events.get(ev, 0) > 0, ev
            audit = await api.get("/admin/audit", COMMISSIONER, limit=50)
            assert audit and all(a["actor"] for a in audit)
            api_log = await api.get("/admin/api-log", COMMISSIONER, limit=5)
            assert api_log and api_log[0]["path"].startswith(W)


def test_water_module_end_to_end():
    asyncio.run(scenario())


if __name__ == "__main__":
    test_water_module_end_to_end()
    print("Water module end-to-end scenario passed")
