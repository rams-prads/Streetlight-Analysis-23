"""
Module 2 (WTR) - Water & Utility Billing API, mounted at /api/v1/water.

The module runs on its own in Release 1: it reads the platform's tenant, ward and zone code lists but does
not exchange data with any other module. Planned links are defined in settings 'integrationLinks' (SRS 3.7).
"""
from fastapi import APIRouter

from . import admin, applications, approvals, arrears, billing, complaints, connections, meters, payments, reports

router = APIRouter(prefix="/water")
router.include_router(connections.router, tags=["Water - Connections"])
router.include_router(applications.router, tags=["Water - Applications"])
router.include_router(meters.router, tags=["Water - Meters & Readings"])
router.include_router(billing.router, tags=["Water - Tariffs & Billing"])
router.include_router(payments.router, tags=["Water - Collection"])
router.include_router(arrears.router, tags=["Water - Arrears & Disconnection"])
router.include_router(approvals.router, tags=["Water - Approvals"])
router.include_router(complaints.router, tags=["Water - Complaints & Illegal Connections"])
router.include_router(reports.router, tags=["Water - Reports & GIS"])
router.include_router(admin.router, tags=["Water - Administration & Integration"])
