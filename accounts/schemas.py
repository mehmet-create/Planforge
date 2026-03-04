from dataclasses import dataclass

@dataclass
class RegisterDTO:
    username: str
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""
    def __post_init__(self):
        self.email = self.email.strip().lower()
        self.username = self.username.strip()
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()

        
@dataclass
class LoginDTO:
    username: str
    password: str
    def __post_init__(self):
        self.username = self.username.strip()

@dataclass
class VerifyCodeDTO:
    user_id: int
    code: str

@dataclass
class ResendCodeDTO:
    user_id: int

@dataclass
class EmailChangeRequestDTO:
    user_id: int
    new_email: str
    current_email: str

    def __post_init__(self):
        if not self.new_email:
            raise ValueError("New email is required.")
        
        self.new_email = self.new_email.strip().lower()
        self.current_email = self.current_email.strip().lower()

        if self.new_email == self.current_email:
            raise ValueError("New email cannot be the same as your current email.")

@dataclass
class VerifyEmailChangeDTO:
    user_id: int
    code: str

@dataclass
class PasswordChangeDTO:
    user_id: int
    old_password: str
    new_password: str
    confirm_new_password: str

    def __post_init__(self):
        if not self.new_password or not self.confirm_new_password:
             raise ValueError("Both password fields are required.")

        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match.")

        if len(self.new_password) < 8:
            raise ValueError("Password must be at least 8 characters long.")

        if self.new_password == self.old_password:
            raise ValueError("New password cannot be the same as the old one.")
        
        if not any(char.isdigit() for char in self.new_password):
            raise ValueError("Password must contain at least one number.")

        if not any(char.isupper() for char in self.new_password):
            raise ValueError("Password must contain at least one uppercase letter.")

@dataclass
class DeleteAccountDTO:
    user_id: int
    password: str

