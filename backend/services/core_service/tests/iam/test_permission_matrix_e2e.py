"""End-to-end test of the real Roles & Permission Matrix (app/api/v1/iam_permissions.py) against a fresh
SQLite database: only a platform administrator may view or change it, and a saved override actually reaches
real PTX/Water enforcement (not just this endpoint's own response).

Run from backend/services/core_service:
    python -m pytest tests/iam -q
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="iam-perm-e2e-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/iam.db"
os.environ["PTX_STORAGE_DIR"] = os.path.join(_TMP, "ptx-storage")
os.environ["WATER_STORAGE_DIR"] = os.path.join(_TMP, "water-storage")
os.environ["ENVIRONMENT"] = "development"

import httpx  # noqa: E402

from app.main import app  # noqa: E402

P = "/api/v1/iam/permissions"
SUPER_ADMIN = ("admin@urban.gov.in", "Admin@123")
OFFICER = ("revenue.officer@gwmc.gov.in", "Ptax@123")
INSPECTOR = ("revenue.inspector@gwmc.gov.in", "Ptax@123")


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
        return r.json()

    async def put(self, path, body, who, expect=200):
        r = await self.c.put(P + path, headers=self.h(who), json=body)
        assert r.status_code == expect, f"PUT {path} -> {r.status_code}: {r.text}"
        return r.json()


def find(items, **match):
    return next(i for i in items if all(i.get(k) == v for k, v in match.items()))


async def scenario():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
            api = Api(client)
            for who in (SUPER_ADMIN, OFFICER, INSPECTOR):
                await api.login(who)

            # ---- only a platform administrator may reach this at all ------------------------------------
            await api.get("/PTX/matrix", OFFICER, expect=403)
            await api.get("/PTX/matrix", INSPECTOR, expect=403)
            await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "survey.review", "role": "revenue_inspector", "granted": True}]},
                         OFFICER, expect=403)

            # ---- a module with no real backend isn't exposed at all --------------------------------------
            await api.get("/GRV/matrix", SUPER_ADMIN, expect=404)

            # ---- the matrix reflects the real PERMISSIONS dict, not fabricated data ----------------------
            matrix = await api.get("/PTX/matrix", SUPER_ADMIN)
            assert matrix["moduleCode"] == "PTX"
            assert {"super_admin", "system_admin", "revenue_officer", "revenue_inspector", "bill_collector"} <= set(matrix["roles"])
            review = find(matrix["permissions"], key="survey.review")
            assert review["group"] == "survey" and review["label"]
            assert "revenue_officer" in review["defaultRoles"] and "revenue_inspector" not in review["defaultRoles"]
            assert review["defaultRoles"] == review["effectiveRoles"] and review["overrides"] == []

            # ---- bad input is rejected before anything is written -----------------------------------------
            await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "not.a.real.key", "role": "revenue_inspector", "granted": True}]},
                         SUPER_ADMIN, expect=400)
            await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "survey.review", "role": "not_a_role", "granted": True}]},
                         SUPER_ADMIN, expect=400)
            await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "survey.review", "role": "super_admin", "granted": False}]},
                         SUPER_ADMIN, expect=400)

            # ---- a saved override shows up in the matrix, and reaches real enforcement (not just this screen) --
            ptx_surveys = lambda who: client.get("/api/v1/ptx/surveys", headers=api.h(who))  # noqa: E731
            assert (await ptx_surveys(INSPECTOR)).status_code == 403  # baseline, same assertion as tests/ptx
            saved = await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "survey.review", "role": "revenue_inspector",
                                                                       "granted": True, "reason": "Pilot"}]}, SUPER_ADMIN)
            review = find(saved["permissions"], key="survey.review")
            assert "revenue_inspector" in review["effectiveRoles"] and review["defaultRoles"] == ["revenue_officer", "super_admin", "system_admin"]
            assert review["overrides"] == [{"role": "revenue_inspector", "granted": True, "reason": "Pilot",
                                            "createdBy": SUPER_ADMIN[0], "effectiveFrom": review["overrides"][0]["effectiveFrom"]}]
            refetched = await api.get("/PTX/matrix", SUPER_ADMIN)  # persisted, not just echoed back
            assert "revenue_inspector" in find(refetched["permissions"], key="survey.review")["effectiveRoles"]
            assert (await ptx_surveys(INSPECTOR)).status_code == 200  # the actual PTX endpoint now allows it

            # ---- reverting (granted: null) removes it from the matrix and from enforcement -----------------
            reverted = await api.put("/PTX/overrides/bulk", {"changes": [{"permissionKey": "survey.review", "role": "revenue_inspector",
                                                                          "granted": None}]}, SUPER_ADMIN)
            review = find(reverted["permissions"], key="survey.review")
            assert review["effectiveRoles"] == review["defaultRoles"] and review["overrides"] == []
            assert (await ptx_surveys(INSPECTOR)).status_code == 403

            # ---- role catalogue spans the named modules, for assigning a user's real role ------------------
            roles = (await api.get("/roles", SUPER_ADMIN, modules="PTX,WTR"))["roles"]
            assert {"bill_collector", "revenue_inspector"} <= set(roles)  # PTX
            assert "water_field_staff" in roles  # WTR


def test_permission_matrix_end_to_end():
    import asyncio
    asyncio.run(scenario())
