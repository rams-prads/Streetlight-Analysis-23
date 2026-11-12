"""End-to-end test of Global User Management's real role assignment (app/api/v1/iam.py's
create_user/update_user_scope/reset_user_password): a created user's primaryRole is validated
against the live PTX/Water role catalogues (not guessed from a decorative role code), and it is
exactly what ends up in users.role - proven by actually signing in as the new user, not just
reading the admin screen's own response back.

Run from backend/services/core_service:
    python -m pytest tests/iam -q
"""
import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="iam-user-e2e-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/iam.db"
os.environ["PTX_STORAGE_DIR"] = os.path.join(_TMP, "ptx-storage")
os.environ["WATER_STORAGE_DIR"] = os.path.join(_TMP, "water-storage")
os.environ["ENVIRONMENT"] = "development"

import httpx  # noqa: E402

from app.main import app  # noqa: E402

API = "/api/v1/iam/users"
SUPER_ADMIN = ("admin@urban.gov.in", "Admin@123")


class Api:
    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.token = None

    async def login(self, who) -> None:
        r = await self.c.post("/api/v1/auth/signin", json={"userName": who[0], "password": who[1]})
        assert r.status_code == 200, r.text
        self.token = r.json()["accessToken"]

    def h(self):
        return {"X-Tenant-ID": "GWMC", "Authorization": f"Bearer {self.token}"}

    async def post(self, path, body, expect=200):
        r = await self.c.post(API + path, headers=self.h(), json=body)
        assert r.status_code == expect, f"POST {path} -> {r.status_code}: {r.text}"
        return r.json()

    async def put(self, path, body, expect=200):
        r = await self.c.put(API + path, headers=self.h(), json=body)
        assert r.status_code == expect, f"PUT {path} -> {r.status_code}: {r.text}"
        return r.json()


async def scenario():
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
            api = Api(client)
            await api.login(SUPER_ADMIN)

            email = f"phase6.{uuid.uuid4().hex[:10]}@gwmc.gov.in"
            created = await api.post("", {"firstName": "Phase6", "lastName": "Tester", "email": email})
            assert created["success"]
            user_id = created["data"]["id"]
            assert created["data"]["userId"]  # the real auth row is linked immediately on creation

            # ---- ambiguous assignment (more than one role, no primaryRole) is rejected -------------------
            await api.put(f"/{user_id}/scope", {
                "assignedRoles": ["bill_collector", "revenue_officer"],
                "ulbTenantId": "GWMC",
            }, expect=400)

            # ---- a primaryRole that no live module recognises is rejected --------------------------------
            await api.put(f"/{user_id}/scope", {
                "assignedRoles": ["bill_collector"],
                "primaryRole": "not_a_real_role",
                "ulbTenantId": "GWMC",
            }, expect=400)

            # ---- a valid, explicit primaryRole is accepted and recorded exactly --------------------------
            updated = await api.put(f"/{user_id}/scope", {
                "assignedRoles": ["bill_collector"],
                "primaryRole": "bill_collector",
                "ulbTenantId": "GWMC",
            })
            assert updated["data"]["primaryRole"] == "bill_collector"

            # ---- that role is what the real auth table carries - proven by actually signing in ------------
            new_pwd = "Phase6@2026"
            reset = await api.post(f"/{user_id}/reset-password", {"newPassword": new_pwd})
            assert reset["success"]

            login = await client.post("/api/v1/auth/signin", json={"userName": email, "password": new_pwd})
            assert login.status_code == 200, login.text
            assert login.json()["user"]["role"] == "bill_collector"

            # ---- platform access always wins, regardless of any assigned role ----------------------------
            platform = await api.put(f"/{user_id}/scope", {
                "platformAccess": True,
                "assignedRoles": ["bill_collector"],
                "primaryRole": "bill_collector",
            })
            assert platform["data"]["primaryRole"] == "super_admin"
            login2 = await client.post("/api/v1/auth/signin", json={"userName": email, "password": new_pwd})
            assert login2.json()["user"]["role"] == "super_admin"


def test_global_user_management_end_to_end():
    import asyncio
    asyncio.run(scenario())
