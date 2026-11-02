"""
Module 1 (PTX) - Property Tax & Revenue Management API, mounted at /api/v1/ptx.

The module runs on its own in Release 1: it reads the platform's tenant, ward, zone and locality code lists but does not
exchange data with any other module. Planned links are defined in settings 'integrationLinks' (SRS 3.7).
"""
from fastapi import APIRouter

from . import admin, approvals, arrears, billing, cases, certificates, citizen, complaints, field, integrations, payments, petitions, properties, remittances, reports

router = APIRouter(prefix="/ptx")
router.include_router(properties.router, tags=["Property Tax - Register"])
router.include_router(cases.router, tags=["Property Tax - Assessment & Changes"])
router.include_router(complaints.router, tags=["Property Tax - Complaints"])
router.include_router(certificates.router, tags=["Property Tax - Certificates"])
router.include_router(petitions.router, tags=["Property Tax - Petitions & Appeals"])
router.include_router(billing.router, tags=["Property Tax - Rates & Demand"])
router.include_router(remittances.router, tags=["Property Tax - Remittance"])
router.include_router(payments.router, tags=["Property Tax - Collection"])
router.include_router(arrears.router, tags=["Property Tax - Arrears & Notices"])
router.include_router(approvals.router, tags=["Property Tax - Approvals"])
router.include_router(reports.router, tags=["Property Tax - Reports & GIS"])
router.include_router(citizen.router, tags=["Property Tax - Citizen"])
router.include_router(field.router, tags=["Property Tax - Field App"])
router.include_router(integrations.router, tags=["Property Tax - Connections"])
router.include_router(admin.router, tags=["Property Tax - Administration & Integration"])
