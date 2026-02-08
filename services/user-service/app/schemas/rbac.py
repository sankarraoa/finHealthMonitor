"""Pydantic models for RBAC API requests and responses."""
from pydantic import BaseModel, EmailStr
from typing import Optional, List


class TenantCreate(BaseModel):
    company_name: str
    tax_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    company_name: str
    tax_id: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    password: Optional[str] = None
    phone: Optional[str] = None
    image_url: Optional[str] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    image_url: Optional[str] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: Optional[str]
    image_url: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    tenants: List[TenantResponse]
    default_tenant: Optional[TenantResponse] = None


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RoleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    is_system_role: str
    
    class Config:
        from_attributes = True


class PermissionCreate(BaseModel):
    resource: str
    action: str
    description: Optional[str] = None


class PermissionResponse(BaseModel):
    id: str
    resource: str
    action: str
    description: Optional[str]
    
    class Config:
        from_attributes = True


class AssignRoleToUser(BaseModel):
    role_id: str


class AssignPermissionToRole(BaseModel):
    permission_id: str
