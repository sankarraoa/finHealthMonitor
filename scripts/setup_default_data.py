"""Script to set up default data for multi-tenant RBAC system."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_session
from app.services import tenant_service, user_service, role_service, permission_service
from app.auth.password import hash_password


def setup_default_data():
    """Set up default tenant, user, roles, and permissions."""
    with get_db_session() as db:
        # Check if getGo tenant already exists
        getgo = tenant_service.get_tenant_by_name(db, "getGo")
        if not getgo:
            # Create getGo tenant
            getgo = tenant_service.create_tenant(
                db,
                company_name="getGo",
                email="info@getgo.ai"
            )
            print(f"Created getGo tenant: {getgo.id}")
            
            # Create default roles for getGo
            roles = role_service.create_default_roles_for_tenant(db, getgo.id, permission_service)
            print(f"Created {len(roles)} default roles for getGo")
        else:
            print(f"getGo tenant already exists: {getgo.id}")
            # Get existing roles
            roles = {r.name: r for r in role_service.list_roles_in_tenant(db, getgo.id)}
        
        # Check if Veda Valli user exists
        veda = user_service.get_user_by_email(db, "veda.valli@getgo.ai")
        if not veda:
            # Create Veda Valli user
            veda = user_service.create_user(
                db,
                email="veda.valli@getgo.ai",
                first_name="Veda",
                last_name="Valli",
                password="password123"  # Default password - should be changed
            )
            print(f"Created Veda Valli user: {veda.id}")
        else:
            print(f"Veda Valli user already exists: {veda.id}")
        
        # Check if Veda is assigned to getGo
        from app.models.rbac import UserTenantRole
        membership = db.query(UserTenantRole).filter(
            UserTenantRole.user_id == veda.id,
            UserTenantRole.tenant_id == getgo.id
        ).first()
        
        if not membership:
            # Assign Veda to getGo as Administrator
            admin_role = roles.get("Administrator")
            if admin_role:
                user_service.add_user_to_tenant(db, veda.id, getgo.id, admin_role.id)
                print(f"Assigned Veda Valli to getGo as Administrator")
            else:
                print("ERROR: Administrator role not found!")
        else:
            print("Veda Valli is already assigned to getGo")
        
        print("\nSetup complete!")
        print(f"Tenant: getGo (ID: {getgo.id})")
        print(f"User: Veda Valli (Email: veda.valli@getgo.ai)")
        print(f"Password: password123")
        print(f"Role: Administrator")


if __name__ == "__main__":
    setup_default_data()
