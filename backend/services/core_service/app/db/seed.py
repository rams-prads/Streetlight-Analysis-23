import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import (
    Tenant, Zone, Ward, Locality, PropertyParcel, Building, PropertyUnit, Owner, User,
    StateTenant, TenantAuditLog, State, District, City, ModuleModel, ComponentModel
)
from app.core.security import hash_password
from app.db.session import engine, Base

logger = logging.getLogger(__name__)

async def seed_initial_data(db: AsyncSession):
    # Check and seed GWMC tenant
    existing_gwmc = await db.scalar(select(Tenant).where(Tenant.tenant_id == "GWMC"))
    if not existing_gwmc:
        logger.info("Seeding initial GWMC municipal data...")

        # Tenant
        tenant = Tenant(
            tenant_id="GWMC",
            name="Greater Warangal Municipal Corporation",
            state_code="TG",
            district="Hanamkonda & Warangal"
        )
        db.add(tenant)
        await db.flush()

        # Zones
        z1 = Zone(tenant_id="GWMC", code="ZONE-1", name="Kazipet Zone")
        z2 = Zone(tenant_id="GWMC", code="ZONE-2", name="Hanamkonda Zone")
        z3 = Zone(tenant_id="GWMC", code="ZONE-3", name="Warangal Zone")
        db.add_all([z1, z2, z3])
        await db.flush()

        # Wards
        w1 = Ward(tenant_id="GWMC", zone_id=z2.id, ward_number=14, ward_name="Subedari", councilor_name="Smt. K. Saritha")
        w2 = Ward(tenant_id="GWMC", zone_id=z2.id, ward_number=22, ward_name="Balasamudram", councilor_name="Sri P. Rajesh")
        w3 = Ward(tenant_id="GWMC", zone_id=z2.id, ward_number=35, ward_name="Nakkalagutta", councilor_name="Sri V. Mohan Rao")
        w4 = Ward(tenant_id="GWMC", zone_id=z1.id, ward_number=48, ward_name="KU Campus Road", councilor_name="Dr. T. Radhika")
        w5 = Ward(tenant_id="GWMC", zone_id=z3.id, ward_number=56, ward_name="Mandi Bazar", councilor_name="Sri M. Srinivas")
        db.add_all([w1, w2, w3, w4, w5])
        await db.flush()

        # Localities
        loc1 = Locality(tenant_id="GWMC", ward_id=w1.id, locality_code="LOC-14-01", locality_name="Postal Colony", pincode="506001")
        loc2 = Locality(tenant_id="GWMC", ward_id=w2.id, locality_code="LOC-22-01", locality_name="Judicial Complex Enclave", pincode="506001")
        loc3 = Locality(tenant_id="GWMC", ward_id=w3.id, locality_code="LOC-35-01", locality_name="Green Meadows Avenue", pincode="506002")
        db.add_all([loc1, loc2, loc3])
        await db.flush()

        # Sample Properties
        sample_props = [
            {
                "ulpin": "TG-GWMC-506001-00123",
                "survey": "142/A",
                "plot": "Plot 12",
                "area": 250.0,
                "ward": w1,
                "loc": loc1,
                "lat": 17.9812,
                "lng": 79.5982,
                "addr": "H.No 2-4-123, Postal Colony, Subedari, Hanamkonda",
                "bldg_name": "Sri Lakshmi Nivas",
                "bldg_type": "Residential",
                "floors": 2,
                "perm": "GWMC/BP/2022/1049",
                "ptin": "1081400234",
                "unit": "G-1",
                "usage": "Residential",
                "carpet": 1150.0,
                "builtup": 1380.0,
                "demand": 4250.0,
                "status": "PAID",
                "owner": "K. Venkateshwarlu",
                "mobile": "9848022331",
                "email": "kvenkat@example.com"
            },
            {
                "ulpin": "TG-GWMC-506001-00456",
                "survey": "198/B",
                "plot": "Plot 45",
                "area": 480.0,
                "ward": w2,
                "loc": loc2,
                "lat": 17.9891,
                "lng": 79.6015,
                "addr": "H.No 3-8-45, Judicial Complex Enclave, Balasamudram",
                "bldg_name": "Balaji Heights Commercial Complex",
                "bldg_type": "Commercial",
                "floors": 4,
                "perm": "GWMC/BP/2021/8874",
                "ptin": "1082200561",
                "unit": "F-101",
                "usage": "Commercial",
                "carpet": 2400.0,
                "builtup": 2950.0,
                "demand": 28400.0,
                "status": "DUE",
                "owner": "Ch. Narayana Rao",
                "mobile": "9440155220",
                "email": "narayana.ch@example.com"
            },
            {
                "ulpin": "TG-GWMC-506002-00789",
                "survey": "88/C",
                "plot": "Plot 88",
                "area": 300.0,
                "ward": w3,
                "loc": loc3,
                "lat": 17.9945,
                "lng": 79.5872,
                "addr": "H.No 1-12-88, Green Meadows Avenue, Nakkalagutta",
                "bldg_name": "Ananya Residency",
                "bldg_type": "Residential",
                "floors": 3,
                "perm": "GWMC/BP/2023/4521",
                "ptin": "1083500912",
                "unit": "Flat-202",
                "usage": "Residential",
                "carpet": 1320.0,
                "builtup": 1600.0,
                "demand": 6800.0,
                "status": "PAID",
                "owner": "P. Sudhakar Reddy",
                "mobile": "9989044112",
                "email": "sudhakar.p@example.com"
            },
            {
                "ulpin": "TG-GWMC-506004-00101",
                "survey": "310/2",
                "plot": "Plot 101",
                "area": 600.0,
                "ward": w4,
                "loc": None,
                "lat": 18.0125,
                "lng": 79.5714,
                "addr": "H.No 5-2-101, Main Road, KU Campus Road, Kazipet",
                "bldg_name": "Kakatiya Tech Park Building A",
                "bldg_type": "Commercial",
                "floors": 5,
                "perm": "GWMC/BP/2020/3310",
                "ptin": "1084800115",
                "unit": "Unit-3A",
                "usage": "Commercial",
                "carpet": 4500.0,
                "builtup": 5400.0,
                "demand": 54600.0,
                "status": "ARREARS",
                "owner": "Kakatiya Infotech Pvt Ltd",
                "mobile": "9701233445",
                "email": "admin@kakatiyainfotech.com"
            },
            {
                "ulpin": "TG-GWMC-506001-00202",
                "survey": "55/1",
                "plot": "Plot 20",
                "area": 180.0,
                "ward": w1,
                "loc": loc1,
                "lat": 17.9825,
                "lng": 79.5991,
                "addr": "H.No 2-4-202, Postal Colony Extension, Subedari",
                "bldg_name": "Sai Ram Nilayam",
                "bldg_type": "Residential",
                "floors": 1,
                "perm": "GWMC/BP/2019/1204",
                "ptin": "1081400889",
                "unit": "Ground-Floor",
                "usage": "Residential",
                "carpet": 850.0,
                "builtup": 1020.0,
                "demand": 2950.0,
                "status": "PAID",
                "owner": "G. Manjula",
                "mobile": "9866123456",
                "email": "manjula.g@example.com"
            }
        ]

        for sp in sample_props:
            p = PropertyParcel(
                tenant_id="GWMC",
                ulpin=sp["ulpin"],
                survey_number=sp["survey"],
                plot_number=sp["plot"],
                total_area_sqyd=sp["area"],
                ward_id=sp["ward"].id,
                locality_id=sp["loc"].id if sp["loc"] else None,
                latitude=sp["lat"],
                longitude=sp["lng"],
                address=sp["addr"]
            )
            db.add(p)
            await db.flush()

            b = Building(
                tenant_id="GWMC",
                parcel_id=p.id,
                building_name=sp["bldg_name"],
                building_type=sp["bldg_type"],
                total_floors=sp["floors"],
                building_permission_no=sp["perm"]
            )
            db.add(b)
            await db.flush()

            u = PropertyUnit(
                tenant_id="GWMC",
                building_id=b.id,
                ptin=sp["ptin"],
                unit_number=sp["unit"],
                usage_category=sp["usage"],
                carpet_area_sqft=sp["carpet"],
                built_up_area_sqft=sp["builtup"],
                occupancy_type="Owner",
                current_demand_amount=sp["demand"],
                tax_status=sp["status"]
            )
            db.add(u)
            await db.flush()

            o = Owner(
                tenant_id="GWMC",
                unit_id=u.id,
                full_name=sp["owner"],
                mobile_number=sp["mobile"],
                email=sp["email"]
            )
            db.add(o)

        # Seed Demo SSO Users with Module Access
        all_19 = "PTX,WTR,GRV,FIN,DMS,TRL,UCH,BPM,TPL,FNC,SWM,ENG,SLM,PRK,INV,HRM,MPM,LGL,GSC"
        demo_users = [
            User(
                tenant_id="GWMC",
                username="admin@urban.gov.in",
                email="admin@urban.gov.in",
                password_hash=hash_password("Admin@123"),
                full_name="Suresh Kumar (State Admin)",
                role="super_admin",
                assigned_modules=all_19
            ),
            User(
                tenant_id="GWMC",
                username="officer@gwmc.gov.in",
                email="officer@gwmc.gov.in",
                password_hash=hash_password("Officer@123"),
                full_name="Ramesh Reddy (Revenue Officer)",
                role="revenue_officer",
                assigned_modules="PTX,WTR,TRL,UCH,MPM,FIN,DMS",
                assigned_zone="Zone-1",
                assigned_ward="Ward-14"
            ),
            User(
                tenant_id="GWMC",
                username="planner@gwmc.gov.in",
                email="planner@gwmc.gov.in",
                password_hash=hash_password("Planner@123"),
                full_name="Ananya Sharma (Town Planning Officer)",
                role="town_planner",
                assigned_modules="BPM,TPL,FNC,DMS,LGL",
                assigned_zone="Zone-2"
            ),
            User(
                tenant_id="GWMC",
                username="citizen@gmail.com",
                email="citizen@gmail.com",
                password_hash=hash_password("Citizen@123"),
                full_name="K. Venkateshwarlu (Citizen)",
                role="citizen",
                assigned_modules="GRV,PTX,WTR,TRL,GSC,DMS",
                assigned_ward="Ward-14"
            )
        ]
        db.add_all(demo_users)

        await db.commit()
        logger.info("GWMC initial data & SSO users seeded successfully!")

    # Check and seed second SaaS Tenant: GHMC (Greater Hyderabad Municipal Corporation)
    existing_ghmc = await db.scalar(select(Tenant).where(Tenant.tenant_id == "GHMC"))
    if not existing_ghmc:
        logger.info("Seeding initial GHMC SaaS tenant data...")
        ghmc_tenant = Tenant(
            tenant_id="GHMC",
            name="Greater Hyderabad Municipal Corporation",
            state_code="TG",
            district="Hyderabad"
        )
        db.add(ghmc_tenant)
        await db.flush()

        gz1 = Zone(tenant_id="GHMC", code="ZONE-KH", name="Khairatabad Zone")
        gz2 = Zone(tenant_id="GHMC", code="ZONE-CH", name="Charminar Zone")
        gz3 = Zone(tenant_id="GHMC", code="ZONE-SC", name="Secunderabad Zone")
        db.add_all([gz1, gz2, gz3])
        await db.flush()

        gw1 = Ward(tenant_id="GHMC", zone_id=gz1.id, ward_number=89, ward_name="Banjara Hills", councilor_name="Sri K. Ramakrishna")
        gw2 = Ward(tenant_id="GHMC", zone_id=gz1.id, ward_number=95, ward_name="Jubilee Hills", councilor_name="Smt. M. Madhavi")
        gw3 = Ward(tenant_id="GHMC", zone_id=gz2.id, ward_number=45, ward_name="Charminar Old City", councilor_name="Md. Farooq Ahmed")
        db.add_all([gw1, gw2, gw3])
        await db.flush()

        gloc1 = Locality(tenant_id="GHMC", ward_id=gw1.id, locality_code="LOC-89-01", locality_name="Road No 12 Commercial Belt", pincode="500034")
        gloc2 = Locality(tenant_id="GHMC", ward_id=gw2.id, locality_code="LOC-95-01", locality_name="Jubilee Enclave Heights", pincode="500033")
        db.add_all([gloc1, gloc2])
        await db.flush()

        ghmc_parcel1 = PropertyParcel(
            tenant_id="GHMC",
            ulpin="TG-GHMC-500034-00891",
            survey_number="210/B",
            plot_number="Plot 89A",
            total_area_sqyd=600.0,
            ward_id=gw1.id,
            locality_id=gloc1.id,
            latitude=17.4156,
            longitude=78.4352,
            address="Plot 89A, Road No 12, Banjara Hills, Hyderabad"
        )
        ghmc_parcel2 = PropertyParcel(
            tenant_id="GHMC",
            ulpin="TG-GHMC-500033-00952",
            survey_number="104/1",
            plot_number="Plot 14",
            total_area_sqyd=450.0,
            ward_id=gw2.id,
            locality_id=gloc2.id,
            latitude=17.4325,
            longitude=78.4071,
            address="Plot 14, Road No 36, Jubilee Hills, Hyderabad"
        )
        db.add_all([ghmc_parcel1, ghmc_parcel2])
        await db.flush()

        gb1 = Building(
            tenant_id="GHMC",
            parcel_id=ghmc_parcel1.id,
            building_name="Banjara Corporate Plaza",
            building_type="Commercial",
            total_floors=5,
            construction_year=2021,
            building_permission_no="GHMC/BP/2021/8912"
        )
        gb2 = Building(
            tenant_id="GHMC",
            parcel_id=ghmc_parcel2.id,
            building_name="Jubilee Heights Villa",
            building_type="Residential",
            total_floors=2,
            construction_year=2023,
            building_permission_no="GHMC/BP/2023/4521"
        )
        db.add_all([gb1, gb2])
        await db.flush()

        gu1 = PropertyUnit(
            tenant_id="GHMC",
            building_id=gb1.id,
            ptin="1009871101",
            unit_number="Suite 101",
            floor_number=1,
            usage_category="Commercial",
            carpet_area_sqft=2800.0,
            built_up_area_sqft=3200.0,
            occupancy_type="Tenant",
            annual_rental_value=720000.0,
            current_demand_amount=72000.0,
            tax_status="PAID"
        )
        gu2 = PropertyUnit(
            tenant_id="GHMC",
            building_id=gb2.id,
            ptin="1009872202",
            unit_number="Villa 1",
            floor_number=0,
            usage_category="Residential",
            carpet_area_sqft=3200.0,
            built_up_area_sqft=3800.0,
            occupancy_type="Owner",
            annual_rental_value=96000.0,
            current_demand_amount=9600.0,
            tax_status="DUE"
        )
        db.add_all([gu1, gu2])
        await db.flush()

        go1 = Owner(
            tenant_id="GHMC",
            unit_id=gu1.id,
            full_name="Apollo Infotech Ltd",
            mobile_number="9849011223",
            email="admin@apolloinfo.com",
            ownership_share=100.0
        )
        go2 = Owner(
            tenant_id="GHMC",
            unit_id=gu2.id,
            full_name="K. Taraka Rao",
            mobile_number="9849099887",
            email="taraka.rao@gmail.com",
            ownership_share=100.0
        )
        db.add_all([go1, go2])

        ghmc_officer = User(
            tenant_id="GHMC",
            username="officer@ghmc.gov.in",
            email="officer@ghmc.gov.in",
            password_hash=hash_password("Officer@123"),
            full_name="S. Narsing Rao (GHMC Revenue Officer)",
            role="revenue_officer",
            assigned_modules="PTX,WTR,TRL,UCH,MPM,FIN,DMS",
            assigned_zone="Khairatabad Zone",
            assigned_ward="Ward-89"
        )
        db.add(ghmc_officer)
        await db.commit()
        logger.info("GHMC SaaS tenant & demo data seeded successfully!")

    # Check and seed Level 1 State Tenants (unconditionally checked)
    existing_st = await db.scalar(select(StateTenant).limit(1))
    if not existing_st:
        logger.info("Seeding Level 1 State Tenants (ADM-T01)...")
        st_tg = StateTenant(
            tenant_id="d47a8b30-1c39-4b62-9e12-4f81014a9001",
            state_name="Telangana",
            state_code="TG",
            tenant_slug="telangana",
            status="Active",
            country="India",
            time_zone="Asia/Kolkata",
            primary_language="English",
            additional_languages=["Telugu", "Urdu", "Hindi"],
            official_state_name="Government of Telangana (CDMA & UDD)",
            state_website="https://cdma.telangana.gov.in",
            administrative_email="director.cdma@telangana.gov.in",
            administrative_phone="+91-40-23302150",
            address="Commissionerate & Directorate of Municipal Administration, AC Guards, Hyderabad, 500004",
            effective_date="2024-06-02",
            notes="Level 1 State Tenant governing 142 ULBs including GHMC and GWMC across 33 districts."
        )
        st_mh = StateTenant(
            tenant_id="e83c9a41-2b48-4c73-af23-5e92125b8002",
            state_name="Maharashtra",
            state_code="MH",
            tenant_slug="maharashtra",
            status="Active",
            country="India",
            time_zone="Asia/Kolkata",
            primary_language="English",
            additional_languages=["Marathi", "Hindi"],
            official_state_name="Urban Development Department, Government of Maharashtra",
            state_website="https://urban.maharashtra.gov.in",
            administrative_email="sec.ud1@maharashtra.gov.in",
            administrative_phone="+91-22-22025211",
            address="Mantralaya, Madam Cama Road, Nariman Point, Mumbai, 400032",
            effective_date="2024-08-15",
            notes="Level 1 State Tenant managing 398 municipal corporations and councils."
        )
        st_ka = StateTenant(
            tenant_id="f94d0b52-3c59-4d84-b034-6f03236c9003",
            state_name="Karnataka",
            state_code="KA",
            tenant_slug="karnataka",
            status="Draft",
            country="India",
            time_zone="Asia/Kolkata",
            primary_language="English",
            additional_languages=["Kannada", "Hindi"],
            official_state_name="Directorate of Municipal Administration, Government of Karnataka",
            state_website="https://municipaladmn.karnataka.gov.in",
            administrative_email="dma.kar@nic.in",
            administrative_phone="+91-80-22861314",
            address="7th Floor, Vishveshwaraiah Towers, Dr. Ambedkar Veedhi, Bengaluru, 560001",
            effective_date="2026-11-01",
            notes="Draft onboarding phase for 281 ULBs and municipal councils."
        )
        st_tr = StateTenant(
            tenant_id="a8d72a4d-0428-4e8c-8f12-78d1039e7646",
            state_name="Tripura",
            state_code="TR",
            tenant_slug="tripura",
            status="Active",
            country="India",
            time_zone="Asia/Kolkata",
            primary_language="Bengali",
            additional_languages=["English", "Kokborok", "Hindi"],
            official_state_name="Municipal Administration Department, Government of Tripura",
            state_website="https://udd.tripura.gov.in",
            administrative_email="sagarsroy1@gmail.com",
            administrative_phone="+91-381-2414051",
            address="UDD Office Complex, Old Secretariat, Agartala, Tripura 799001",
            effective_date="2026-01-01",
            notes="Tripura State Municipal Administration governing 20 ULBs."
        )
        db.add_all([st_tg, st_mh, st_ka, st_tr])
        await db.flush()

        audit1 = TenantAuditLog(
            tenant_id=st_tg.tenant_id,
            action="ACTIVATED",
            performed_by="admin@urban.gov.in",
            details="Telangana Level 1 State Tenant provisioned with 142 ULBs and 19 module subscriptions.",
            ip_address="10.0.1.15"
        )
        audit2 = TenantAuditLog(
            tenant_id=st_mh.tenant_id,
            action="ACTIVATED",
            performed_by="admin@urban.gov.in",
            details="Maharashtra Level 1 State Tenant provisioned with Mantralaya root credentials.",
            ip_address="10.0.1.15"
        )
        audit3 = TenantAuditLog(
            tenant_id=st_ka.tenant_id,
            action="DRAFT_SAVED",
            performed_by="admin@urban.gov.in",
            details="Karnataka state tenant profile drafted. Awaiting state gazette notification.",
            ip_address="10.0.1.20"
        )
        audit4 = TenantAuditLog(
            tenant_id=st_tr.tenant_id,
            action="ACTIVATED",
            performed_by="admin@urban.gov.in",
            details="Tripura State Municipal Administration provisioned.",
            ip_address="10.0.1.22"
        )
        db.add_all([audit1, audit2, audit3, audit4])
        await db.commit()
        logger.info("Level 1 State Tenants and audit trails seeded successfully!")

    # Check and seed master States, Districts, Cities tables
    existing_state = await db.scalar(select(State).limit(1))
    if not existing_state:
        logger.info("Seeding Master States, Districts, and Cities database tables...")
        from app.api.v1.tenants import MASTER_INDIAN_STATES
        
        # 1. Seed all 36 States/UTs
        for s in MASTER_INDIAN_STATES:
            st_obj = State(
                code=s["code"],
                name=s["name"],
                official_name=s["officialName"],
                default_slug=s["defaultSlug"],
                primary_language=s["primaryLanguage"],
                additional_languages=s.get("additionalLanguages", []),
                zone=s.get("zone")
            )
            db.add(st_obj)
        await db.flush()

        # 2. Seed Districts
        districts_data = [
            # Tripura
            {"state_code": "TR", "code": "TR-WT", "name": "West Tripura", "headquarters": "Agartala"},
            {"state_code": "TR", "code": "TR-GM", "name": "Gomati", "headquarters": "Udaipur"},
            {"state_code": "TR", "code": "TR-ST", "name": "South Tripura", "headquarters": "Belonia"},
            {"state_code": "TR", "code": "TR-DH", "name": "Dhalai", "headquarters": "Ambassa"},
            {"state_code": "TR", "code": "TR-NT", "name": "North Tripura", "headquarters": "Dharmanagar"},
            {"state_code": "TR", "code": "TR-UK", "name": "Unakoti", "headquarters": "Kailashahar"},
            {"state_code": "TR", "code": "TR-KH", "name": "Khowai", "headquarters": "Khowai"},
            {"state_code": "TR", "code": "TR-SP", "name": "Sepahijala", "headquarters": "Bishramganj"},
            # Telangana
            {"state_code": "TG", "code": "TG-HY", "name": "Hyderabad", "headquarters": "Hyderabad"},
            {"state_code": "TG", "code": "TG-HK", "name": "Hanamkonda", "headquarters": "Hanamkonda"},
            {"state_code": "TG", "code": "TG-WL", "name": "Warangal", "headquarters": "Warangal"},
            {"state_code": "TG", "code": "TG-MM", "name": "Medchal-Malkajgiri", "headquarters": "Shamirpet"},
            {"state_code": "TG", "code": "TG-RR", "name": "Rangareddy", "headquarters": "Shamshabad"},
            {"state_code": "TG", "code": "TG-NZ", "name": "Nizamabad", "headquarters": "Nizamabad"},
            {"state_code": "TG", "code": "TG-KM", "name": "Karimnagar", "headquarters": "Karimnagar"},
            # Maharashtra
            {"state_code": "MH", "code": "MH-MC", "name": "Mumbai City", "headquarters": "Mumbai"},
            {"state_code": "MH", "code": "MH-MS", "name": "Mumbai Suburban", "headquarters": "Bandra"},
            {"state_code": "MH", "code": "MH-PU", "name": "Pune", "headquarters": "Pune"},
            {"state_code": "MH", "code": "MH-TH", "name": "Thane", "headquarters": "Thane"},
            {"state_code": "MH", "code": "MH-NG", "name": "Nagpur", "headquarters": "Nagpur"},
            {"state_code": "MH", "code": "MH-NS", "name": "Nashik", "headquarters": "Nashik"},
            # Karnataka
            {"state_code": "KA", "code": "KA-BU", "name": "Bengaluru Urban", "headquarters": "Bengaluru"},
            {"state_code": "KA", "code": "KA-MY", "name": "Mysuru", "headquarters": "Mysuru"},
            {"state_code": "KA", "code": "KA-DH", "name": "Dharwad", "headquarters": "Hubballi"},
        ]

        district_map = {}
        for d in districts_data:
            dist_obj = District(
                state_code=d["state_code"],
                code=d["code"],
                name=d["name"],
                headquarters=d["headquarters"]
            )
            db.add(dist_obj)
            district_map[d["code"]] = dist_obj
        await db.flush()

        # 3. Seed Cities / ULBs
        cities_data = [
            # Tripura
            {"state_code": "TR", "district_code": "TR-WT", "name": "Agartala", "ulb_type": "Municipal Corporation", "ulb_code": "TR-AMC-001"},
            {"state_code": "TR", "district_code": "TR-NT", "name": "Dharmanagar", "ulb_type": "Municipal Council", "ulb_code": "TR-DMC-002"},
            {"state_code": "TR", "district_code": "TR-GM", "name": "Udaipur", "ulb_type": "Municipal Council", "ulb_code": "TR-UMC-003"},
            {"state_code": "TR", "district_code": "TR-UK", "name": "Kailashahar", "ulb_type": "Municipal Council", "ulb_code": "TR-KMC-004"},
            {"state_code": "TR", "district_code": "TR-ST", "name": "Belonia", "ulb_type": "Municipal Council", "ulb_code": "TR-BMC-005"},
            # Telangana
            {"state_code": "TG", "district_code": "TG-HY", "name": "Greater Hyderabad (GHMC)", "ulb_type": "Municipal Corporation", "ulb_code": "TG-GHMC-001"},
            {"state_code": "TG", "district_code": "TG-HK", "name": "Greater Warangal (GWMC)", "ulb_type": "Municipal Corporation", "ulb_code": "TG-GWMC-002"},
            {"state_code": "TG", "district_code": "TG-NZ", "name": "Nizamabad", "ulb_type": "Municipal Corporation", "ulb_code": "TG-NMC-003"},
            {"state_code": "TG", "district_code": "TG-KM", "name": "Karimnagar", "ulb_type": "Municipal Corporation", "ulb_code": "TG-KMC-004"},
            # Maharashtra
            {"state_code": "MH", "district_code": "MH-MC", "name": "Brihanmumbai (MCGM)", "ulb_type": "Municipal Corporation", "ulb_code": "MH-MCGM-001"},
            {"state_code": "MH", "district_code": "MH-PU", "name": "Pune (PMC)", "ulb_type": "Municipal Corporation", "ulb_code": "MH-PMC-002"},
            {"state_code": "MH", "district_code": "MH-TH", "name": "Thane (TMC)", "ulb_type": "Municipal Corporation", "ulb_code": "MH-TMC-003"},
            {"state_code": "MH", "district_code": "MH-NG", "name": "Nagpur (NMC)", "ulb_type": "Municipal Corporation", "ulb_code": "MH-NMC-004"},
            # Karnataka
            {"state_code": "KA", "district_code": "KA-BU", "name": "Bruhat Bengaluru (BBMP)", "ulb_type": "Municipal Corporation", "ulb_code": "KA-BBMP-001"},
            {"state_code": "KA", "district_code": "KA-MY", "name": "Mysuru (MCC)", "ulb_type": "Municipal Corporation", "ulb_code": "KA-MCC-002"},
            {"state_code": "KA", "district_code": "KA-DH", "name": "Hubballi-Dharwad (HDMC)", "ulb_type": "Municipal Corporation", "ulb_code": "KA-HDMC-003"},
        ]

        for c in cities_data:
            dist_parent = district_map.get(c["district_code"])
            city_obj = City(
                state_code=c["state_code"],
                district_id=dist_parent.id if dist_parent else None,
                name=c["name"],
                ulb_type=c["ulb_type"],
                ulb_code=c["ulb_code"]
            )
            db.add(city_obj)
        
        await db.commit()
        logger.info("States, Districts, and Cities seeded successfully in database!")

    # Check and seed 19 master modules catalogue
    existing_mod = await db.scalar(select(ModuleModel).where(ModuleModel.code == "PTX"))
    if not existing_mod:
        logger.info("Seeding 19 statutory municipal modules and components...")
        modules_seed_data = [
            {
                "code": "PTX", "name": "Property Tax & Revenue Management",
                "category": "Revenue & Billing", "icon": "ri-money-dollar-circle-line",
                "description": "Property assessment, mutations, GIS survey reconciliation, demand generation, collection, and grievance appeals.",
                "display_order": 1, "version": "2.4.0",
                "components": [
                    ("PTX-P01", "Property registration and identification", "Process", "/revenue/ptx/register"),
                    ("PTX-P02", "Legacy data onboarding and state sync", "Service", "/revenue/ptx/migration"),
                    ("PTX-P03", "Property survey and GIS reconciliation", "Process", "/revenue/ptx/gis"),
                    ("PTX-P04", "Property data correction", "Process", "/revenue/ptx/correction"),
                    ("PTX-P05", "New assessment – built property", "Process", "/revenue/ptx/new-assessment"),
                    ("PTX-P06", "Self-assessment by owner", "Process", "/revenue/ptx/self-assessment"),
                    ("PTX-P07", "Apartment / multi-unit assessment", "Process", "/revenue/ptx/apartments"),
                    ("PTX-P08", "Vacant land tax assessment", "Process", "/revenue/ptx/vlt"),
                    ("PTX-P09", "Reassessment & usage occupancy change", "Process", "/revenue/ptx/reassessment"),
                    ("PTX-P10", "General revision of rates and zones", "Workflow", "/revenue/ptx/rates"),
                    ("PTX-P14", "Auto-mutation from registration", "Service", "/revenue/ptx/mutation-auto"),
                    ("PTX-P18", "Periodic demand generation", "Service", "/revenue/ptx/demand"),
                    ("PTX-P21", "Payment collection & e-receipts", "Process", "/revenue/ptx/collection"),
                    ("PTX-P30", "Dashboards, DCB and compliance reporting", "Report", "/revenue/ptx/dcb")
                ]
            },
            {
                "code": "WTR", "name": "Water, Sewerage & Utility Billing",
                "category": "Revenue & Billing", "icon": "ri-drop-line",
                "description": "Drinking water connection sanction, AMR meter reading, spot billing, NRW accounting, and grievance handling.",
                "display_order": 2, "version": "2.1.0",
                "components": [
                    ("WTR-W01", "New water connection sanction", "Process", "/utilities/wtr/new-connection"),
                    ("WTR-W02", "New sewerage / UGD connection", "Process", "/utilities/wtr/sewerage"),
                    ("WTR-W06", "Ownership transfer & tap category change", "Process", "/utilities/wtr/transfer"),
                    ("WTR-W11", "Meter installation & asset register", "Process", "/utilities/wtr/meters"),
                    ("WTR-W12", "Meter reading & spot billing", "Process", "/utilities/wtr/spot-billing"),
                    ("WTR-W15", "Tariff and volumetric billing setup", "Workflow", "/utilities/wtr/tariffs"),
                    ("WTR-W19", "Utility bill collection & online gateway", "Process", "/utilities/wtr/collection"),
                    ("WTR-W23", "Bulk water accounting & NRW analytics", "Report", "/utilities/wtr/nrw")
                ]
            },
            {
                "code": "GRV", "name": "Citizen Service Desk, Grievance & RTI",
                "category": "Citizen Engagement & Welfare", "icon": "ri-customer-service-2-line",
                "description": "Omnichannel citizen grievances, SLA escalation matrix, RTI application lifecycle, and call centre dispatch.",
                "display_order": 3, "version": "3.0.0",
                "components": [
                    ("GRV-G01", "Citizen grievance registration (Omnichannel)", "Process", "/citizen/grv/register"),
                    ("GRV-G02", "Automated department triage & ticket routing", "Service", "/citizen/grv/triage"),
                    ("GRV-G03", "Field inspector inspection & photo resolution", "Process", "/citizen/grv/field-dispatch"),
                    ("GRV-G04", "SLA escalation & nodal officer reminders", "Service", "/citizen/grv/sla"),
                    ("GRV-G05", "Citizen feedback, rating & reopen requests", "Process", "/citizen/grv/feedback"),
                    ("GRV-G06", "Right to Information (RTI) filing & tracking", "Process", "/citizen/grv/rti")
                ]
            },
            {
                "code": "FIN", "name": "Finance & Accounting",
                "category": "Finance & Administration", "icon": "ri-bank-line",
                "description": "Double-entry municipal accounting system (NMAM compliant), budget allocation, bill passing, and treasury bank reconciliation.",
                "display_order": 4, "version": "1.8.0",
                "components": [
                    ("FIN-F01", "Chart of accounts & budget head configuration", "Workflow", "/finance/coa"),
                    ("FIN-F02", "Annual municipal budget preparation & sanction", "Process", "/finance/budget"),
                    ("FIN-F03", "General ledger & double-entry journal vouchers", "Process", "/finance/ledger"),
                    ("FIN-F04", "Contractor & vendor bill processing", "Process", "/finance/bills"),
                    ("FIN-F05", "Automated bank reconciliation statement (BRS)", "Service", "/finance/brs"),
                    ("FIN-F06", "Financial statements & NMAM compliance reports", "Report", "/finance/reports")
                ]
            },
            {
                "code": "TRL", "name": "Trade Licence Management",
                "category": "Revenue & Billing", "icon": "ri-store-2-line",
                "description": "Trade classification, commercial establishment licensing, sanitary inspection NOC, and fee collection.",
                "display_order": 5, "version": "2.0.0",
                "components": [
                    ("TRL-T01", "New trade licence application", "Process", "/licensing/trl/apply"),
                    ("TRL-T02", "Sanitary inspection & scrutiny", "Process", "/licensing/trl/scrutiny"),
                    ("TRL-T03", "Annual renewal & automated penalty", "Service", "/licensing/trl/renewal"),
                    ("TRL-T04", "Trade suspension & seizure notices", "Process", "/licensing/trl/enforcement")
                ]
            },
            {
                "code": "UCH", "name": "User Charges Management",
                "category": "Revenue & Billing", "icon": "ri-exchange-dollar-line",
                "description": "Sanitation fees, bulk waste generator charges, market rents, and advertisement display fees.",
                "display_order": 6, "version": "1.5.0",
                "components": [
                    ("UCH-U01", "Commercial user charge master definition", "Workflow", "/revenue/uch/master"),
                    ("UCH-U02", "Door-to-door sanitation fee collection", "Process", "/revenue/uch/sanitation"),
                    ("UCH-U03", "Bulk generator monthly billing", "Service", "/revenue/uch/bulk-billing")
                ]
            },
            {
                "code": "SWM", "name": "Solid Waste Management",
                "category": "Infrastructure & Field Operations", "icon": "ri-delete-bin-line",
                "description": "GPS vehicle fleet tracking, route compliance, RFID bin emptying, transfer station weighbridge, and dumpsite monitoring.",
                "display_order": 7, "version": "2.2.0",
                "components": [
                    ("SWM-S01", "Sanitation micro-route zoning & beat mapping", "Workflow", "/swm/routes"),
                    ("SWM-S02", "GPS fleet tracking & route deviation alert", "Service", "/swm/tracking"),
                    ("SWM-S03", "Weighbridge gross & tare reconciliation", "Process", "/swm/weighbridge"),
                    ("SWM-S04", "Compost plant & recycling ledger", "Process", "/swm/processing")
                ]
            },
            {
                "code": "HRM", "name": "Payroll & HR Management",
                "category": "Finance & Administration", "icon": "ri-team-line",
                "description": "Biometric attendance, service book record, salary generation, pension fund, and GPF/NPS deductions.",
                "display_order": 8, "version": "2.0.0",
                "components": [
                    ("HRM-H01", "Municipal employee electronic service book", "Process", "/hr/service-book"),
                    ("HRM-H02", "Biometric & geotagged field attendance", "Service", "/hr/attendance"),
                    ("HRM-H03", "Automated monthly payroll & salary slips", "Service", "/hr/payroll"),
                    ("HRM-H04", "Pension, gratuity & retirement settlement", "Process", "/hr/pension")
                ]
            },
            {
                "code": "DMS", "name": "Document Management System",
                "category": "Finance & Administration", "icon": "ri-folder-open-line",
                "description": "Centralized file movement (e-Office), digital signatures, dispatch register, and permanent archiving.",
                "display_order": 9, "version": "1.7.0",
                "components": [
                    ("DMS-D01", "E-file creation & note sheet lifecycle", "Process", "/dms/e-file"),
                    ("DMS-D02", "Aadhaar / token digital signing service", "Service", "/dms/signing"),
                    ("DMS-D03", "Inward / outward register (Tapal)", "Process", "/dms/tapal")
                ]
            },
            {
                "code": "ENG", "name": "Engineering Project Management System",
                "category": "Infrastructure & Field Operations", "icon": "ri-hammer-line",
                "description": "Civil works estimate, administrative sanction, e-tendering, electronic measurement book (e-MB), and contractor bills.",
                "display_order": 10, "version": "2.3.0",
                "components": [
                    ("ENG-E01", "Work estimate & administrative sanction (AS)", "Process", "/engineering/estimate"),
                    ("ENG-E02", "E-tender publishing & technical scrutiny", "Process", "/engineering/tendering"),
                    ("ENG-E03", "Geotagged electronic measurement book (e-MB)", "Process", "/engineering/emb"),
                    ("ENG-E04", "Running account (RA) contractor bill generation", "Process", "/engineering/bills")
                ]
            },
            {
                "code": "BPM", "name": "Building Permission Management",
                "category": "Planning & Regulation", "icon": "ri-building-4-line",
                "description": "Automated CAD plan scrutiny (APDA/TS-bPASS), setback verification, compound fee calculation, and occupancy certificate.",
                "display_order": 11, "version": "3.1.0",
                "components": [
                    ("BPM-B01", "Online building permit application & fee calculation", "Process", "/planning/bpm/apply"),
                    ("BPM-B02", "Automated CAD / DWG drawing scrutiny engine", "Service", "/planning/bpm/cad-scrutiny"),
                    ("BPM-B03", "Site inspection & setback geo-verification", "Process", "/planning/bpm/inspection"),
                    ("BPM-B04", "Occupancy certificate (OC) issuance", "Process", "/planning/bpm/oc")
                ]
            },
            {
                "code": "SLM", "name": "Street Light Management",
                "category": "Infrastructure & Field Operations", "icon": "ri-lightbulb-line",
                "description": "CCMS smart panel monitoring, automated on/off scheduling, fault detection, and energy savings ledger.",
                "display_order": 12, "version": "1.4.0",
                "components": [
                    ("SLM-L01", "CCMS smart switchboard feeder telemetry", "Service", "/lights/ccms"),
                    ("SLM-L02", "Dark spot GIS mapping & citizen light complaint", "Process", "/lights/complaints"),
                    ("SLM-L03", "LED fixture replacement & warranty inventory", "Process", "/lights/maintenance")
                ]
            },
            {
                "code": "TPL", "name": "Town Planning",
                "category": "Planning & Regulation", "icon": "ri-compass-3-line",
                "description": "Master plan zoning, land use certificates, layout approvals, change of land use (CLU), and road widening acquisition.",
                "display_order": 13, "version": "2.0.0",
                "components": [
                    ("TPL-T01", "Land use certificate (LUC) application", "Process", "/planning/tpl/luc"),
                    ("TPL-T02", "Residential / commercial layout layout sanction", "Process", "/planning/tpl/layouts"),
                    ("TPL-T03", "Change of land use (CLU) recommendation", "Workflow", "/planning/tpl/clu")
                ]
            },
            {
                "code": "PRK", "name": "Parks & Horticulture Management",
                "category": "Infrastructure & Field Operations", "icon": "ri-plant-line",
                "description": "Public park asset registry, urban forestry plantation count, seasonal maintenance, and facility booking.",
                "display_order": 14, "version": "1.2.0",
                "components": [
                    ("PRK-K01", "Municipal park and garden asset registry", "Process", "/parks/registry"),
                    ("PRK-K02", "Tree census, geotagging & survival audit", "Process", "/parks/tree-census"),
                    ("PRK-K03", "Community hall / park open lawn booking", "Process", "/parks/bookings")
                ]
            },
            {
                "code": "MPM", "name": "Municipal Property Management",
                "category": "Revenue & Billing", "icon": "ri-hotel-line",
                "description": "Estates & shopping complex leasing, auction management, rent collection, lease deed renewal, and eviction notices.",
                "display_order": 15, "version": "1.9.0",
                "components": [
                    ("MPM-M01", "Municipal shopping complex shop allotment", "Process", "/estates/allotment"),
                    ("MPM-M02", "Monthly commercial shop rent demand & collection", "Service", "/estates/rent"),
                    ("MPM-M03", "Lease agreement expiry & public e-auction", "Workflow", "/estates/auction")
                ]
            },
            {
                "code": "LGL", "name": "Legal Case Management",
                "category": "Planning & Regulation", "icon": "ri-scales-3-line",
                "description": "High court / civil court case repository, advocate vakalatnama, counter affidavit tracking, and injunction compliance.",
                "display_order": 16, "version": "1.6.0",
                "components": [
                    ("LGL-C01", "Court case entry & court proceeding timeline", "Process", "/legal/cases"),
                    ("LGL-C02", "Advocate panel assignment & hearing calendar", "Process", "/legal/advocates"),
                    ("LGL-C03", "Stay order & interim injunction compliance tracker", "Process", "/legal/stays")
                ]
            },
            {
                "code": "INV", "name": "Inventory & Stores Management",
                "category": "Finance & Administration", "icon": "ri-archive-line",
                "description": "Central municipal store items, goods receipt note (GRN), departmental indent issuance, stock valuation, and re-order level alerts.",
                "display_order": 17, "version": "1.5.0",
                "components": [
                    ("INV-I01", "Store items master & barcode/RFID catalog", "Process", "/inventory/items"),
                    ("INV-I02", "Goods receipt note (GRN) inspection & inward", "Process", "/inventory/grn"),
                    ("INV-I03", "Departmental material indent & store issue voucher", "Process", "/inventory/issues")
                ]
            },
            {
                "code": "FNC", "name": "Fire NOC Management",
                "category": "Planning & Regulation", "icon": "ri-fire-line",
                "description": "Provisional & final Fire NOC application, fire safety equipment checklist inspection, and annual renewal audits.",
                "display_order": 18, "version": "1.3.0",
                "components": [
                    ("FNC-N01", "Provisional fire safety NOC application", "Process", "/fire/provisional-noc"),
                    ("FNC-N02", "Joint inspection with State Fire Service", "Process", "/fire/inspection"),
                    ("FNC-N03", "Final Fire NOC grant & annual renewal compliance", "Process", "/fire/final-noc")
                ]
            },
            {
                "code": "GSC", "name": "Government Schemes Management",
                "category": "Citizen Engagement & Welfare", "icon": "ri-hand-heart-line",
                "description": "Urban Community Development (UCD), PMAY housing subsidies, PM SVANidhi street vendor loans, and DAY-NULM SHG revolving funds.",
                "display_order": 19, "version": "2.0.0",
                "components": [
                    ("GSC-S01", "Central / State scheme eligibility & registration", "Process", "/schemes/register"),
                    ("GSC-S02", "PM SVANidhi street vendor verification & recommendation", "Process", "/schemes/svanidhi"),
                    ("GSC-S03", "Direct benefit transfer (DBT) subsidy disbursement", "Service", "/schemes/dbt")
                ]
            }
        ]

        for m_data in modules_seed_data:
            mod_obj = ModuleModel(
                name=m_data["name"],
                code=m_data["code"],
                category=m_data["category"],
                icon=m_data["icon"],
                description=m_data["description"],
                display_order=m_data["display_order"],
                module_version=m_data["version"],
                status="Published",
                dependencies=[],
                minimum_platform_version="1.0.0",
                effective_from="2026-01-01"
            )
            db.add(mod_obj)

            for comp_code, comp_name, comp_type, route in m_data["components"]:
                actions = ["VIEW", "CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "MANAGE"]
                c_obj = ComponentModel(
                    parent_module_code=m_data["code"],
                    code=comp_code,
                    name=comp_name,
                    description=f"{comp_name} - Granular RBAC process under {m_data['code']}",
                    component_type=comp_type,
                    route_path=route,
                    frontend_permission_key=f"{comp_code}:VIEW",
                    backend_api_permission_key=f"{m_data['code']}:{comp_code}:EXECUTE",
                    supported_actions=actions,
                    dependencies=[],
                    status="Published",
                    display_order=1
                )
                db.add(c_obj)

        await db.commit()
        logger.info("Successfully seeded 19 municipal modules and core components in master catalogue!")



