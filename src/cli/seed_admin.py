import asyncio
from src.core.database import AsyncSessionLocal


async def _seed_admin() -> None:
    import getpass
    from src.core.security import hash_password
    from src.domains.users.crud import create, get_by_email
    from src.domains.users.schemas import UserCreate
    from src.core.dependencies import UserRole

    print("=== Seed Platform Admin ===")
    email = (await asyncio.to_thread(input, "Email: ")).strip()
    if not email:
        print("Email cannot be empty.")
        return

    password = await asyncio.to_thread(getpass.getpass, "Password: ")
    confirm = await asyncio.to_thread(getpass.getpass, "Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    tenant_raw = (
        await asyncio.to_thread(
            input, "Tenant ID (leave blank for platform admin, no tenant): "
        )
    ).strip()
    tenant_id = None
    if tenant_raw:
        from uuid import UUID as _UUID

        try:
            tenant_id = _UUID(tenant_raw)
        except ValueError:
            print("Invalid UUID for tenant_id.")
            return

    async with AsyncSessionLocal() as db:
        existing = await get_by_email(db, email)
        if existing:
            print(f"A user with email {email!r} already exists (id={existing.id}).")
            return

        data = UserCreate(
            email=email,
            role=UserRole.PLATFORM_ADMIN,
            tenant_id=tenant_id,
        )
        user = await create(db, data, hash_password(password))
        print("\nPlatform admin created successfully.")
        print(f"  id    : {user.id}")
        print(f"  email : {user.email}")
        print(f"  role  : {user.role}")


def seed_admin() -> None:
    """Entry-point for the seed-admin CLI command."""
    asyncio.run(_seed_admin())
