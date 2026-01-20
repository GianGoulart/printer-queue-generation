"""Database seeding script."""

from app.database import SessionLocal
from app.models.tenant import Tenant
from app.models.machine import Machine
from app.models.sizing_profile import SizingProfile
from app.models.storage_config import TenantStorageConfig


def seed_database():
    """Seed database with initial data."""
    db = SessionLocal()

    try:
        # Check if tenant already exists
        existing_tenant = db.query(Tenant).filter_by(name="Demo Tenant").first()
        
        if existing_tenant:
            print("Database already seeded. Skipping.")
            return

        # Create demo tenant
        tenant = Tenant(
            name="Demo Tenant",
            is_active=True
        )
        db.add(tenant)
        db.flush()  # Get the tenant ID

        print(f"Created tenant: {tenant.name} (ID: {tenant.id})")

        # Create demo machine
        machine = Machine(
            tenant_id=tenant.id,
            name="Demo DTF Printer",
            max_width_mm=600.0,
            max_length_mm=2500.0,
            min_dpi=300
        )
        db.add(machine)
        print(f"Created machine: {machine.name}")

        # Create sizing profiles
        sizing_profiles = [
            SizingProfile(tenant_id=tenant.id, size_label="P", target_width_mm=80.0),
            SizingProfile(tenant_id=tenant.id, size_label="M", target_width_mm=100.0),
            SizingProfile(tenant_id=tenant.id, size_label="G", target_width_mm=120.0),
            SizingProfile(tenant_id=tenant.id, size_label="GG", target_width_mm=140.0),
        ]

        for profile in sizing_profiles:
            db.add(profile)
            print(f"Created sizing profile: {profile.size_label} ({profile.target_width_mm}mm)")

        # Create storage config (local for development)
        storage_config = TenantStorageConfig(
            tenant_id=tenant.id,
            provider="local",
            base_path="/tmp/printer-queue-assets/tenant-1",
            credentials_encrypted=None  # No credentials needed for local
        )
        db.add(storage_config)
        print(f"Created storage config: {storage_config.provider} at {storage_config.base_path}")

        db.commit()
        print("\n✓ Database seeded successfully!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting database seeding...")
    seed_database()
