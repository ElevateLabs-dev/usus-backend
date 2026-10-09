import asyncio
import getpass

from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.core.dependencies import UserRole
from src.core.security import hash_password
from src.domains.scenarios.crud import CRUDScenario
from src.domains.scenarios.models import Scenario
from src.domains.scenarios.service import ScenarioService
from src.domains.tenants.crud import tenant as tenant_repo
from src.domains.tenants.models import Tenant
from src.domains.tenants.schemas import TenantCreate
from src.domains.users.crud import user as user_repo
from src.domains.users.schemas import UserCreate

DEFAULT_ORG_NAME = "Usus Demo Org"

# Roles a tenant user can be seeded with (platform admins use seed-admin instead).
_TENANT_ROLES = {
    "trainee": UserRole.TRAINEE,
    "manager": UserRole.MANAGER,
    "company_admin": UserRole.COMPANY_ADMIN,
}


async def _seed_demo() -> None:
    print("=== Seed Organization (Tenant) + User + Scenarios ===")

    org_name = (
        await asyncio.to_thread(input, f"Organization name [{DEFAULT_ORG_NAME}]: ")
    ).strip() or DEFAULT_ORG_NAME

    email = (await asyncio.to_thread(input, "User email: ")).strip()
    if not email:
        print("Email cannot be empty.")
        return

    role_raw = (
        await asyncio.to_thread(
            input, "Role (trainee / manager / company_admin) [trainee]: "
        )
    ).strip().lower() or "trainee"
    role = _TENANT_ROLES.get(role_raw)
    if role is None:
        print(f"Invalid role {role_raw!r}.")
        return

    async with AsyncSessionLocal() as db:
        existing_user = await user_repo.get_by_email(db, email)
        if existing_user:
            print(
                f"A user with email {email!r} already exists "
                f"(tenant_id={existing_user.tenant_id}). Nothing created."
            )
            return

        password = await asyncio.to_thread(getpass.getpass, "Password: ")
        confirm = await asyncio.to_thread(getpass.getpass, "Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            return
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return

        # Reuse the organization if it already exists, so the command is re-runnable.
        result = await db.execute(select(Tenant).where(Tenant.name == org_name))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = await tenant_repo.create(db, obj_in=TenantCreate(name=org_name))
            print(f"Created organization {org_name!r}.")
        else:
            print(f"Using existing organization {org_name!r}.")

        user = await user_repo.create(
            db,
            obj_in=UserCreate(email=email, role=role, tenant_id=tenant.id),
            hashed_password=hash_password(password),
        )

        scenario_service = ScenarioService(CRUDScenario(Scenario))
        scenarios = await scenario_service.seed_defaults(db, tenant.id)

        print("\nDone.")
        print(f"  organization : {tenant.name}")
        print(f"  tenant_id    : {tenant.id}")
        print(f"  user         : {user.email} ({user.role})")
        print(f"  scenarios    : {len(scenarios)}")
        print("\nSign in with this email and password; no tenant ID is needed.")


def seed_demo() -> None:
    """Entry-point for the seed-demo CLI command."""
    asyncio.run(_seed_demo())
