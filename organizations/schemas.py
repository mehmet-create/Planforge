# DTOs for organization operations.
# Same pattern as accounts/schemas.py

from dataclasses import dataclass


@dataclass
class CreateOrganizationDTO:
    name: str
    created_by_id: int

    def __post_init__(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Organization name cannot be empty.")
        if len(self.name) > 150:
            raise ValueError("Organization name cannot exceed 150 characters.")


@dataclass
class UpdateOrganizationDTO:
    organization_id: int
    acting_user_id: int
    name: str

    def __post_init__(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Organization name cannot be empty.")
        if len(self.name) > 150:
            raise ValueError("Organization name cannot exceed 150 characters.")


@dataclass
class InviteMemberDTO:
    organization_id: int
    acting_user_id: int   # the user performing the invite (must be owner or admin)
    target_username: str  # the user being invited
    role: str = "member"

    def __post_init__(self):
        self.target_username = self.target_username.strip()
        valid_roles = {"owner", "admin", "member"}
        if self.role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")


@dataclass
class RemoveMemberDTO:
    organization_id: int
    acting_user_id: int   # who is performing the removal
    target_user_id: int   # who is being removed


@dataclass
class ChangeMemberRoleDTO:
    organization_id: int
    acting_user_id: int
    target_user_id: int
    new_role: str

    def __post_init__(self):
        valid_roles = {"owner", "admin", "member"}
        if self.new_role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")


@dataclass
class DeleteOrganizationDTO:
    organization_id: int
    acting_user_id: int