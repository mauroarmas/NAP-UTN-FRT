from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: str | None = None
    rol: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginWith2FARequest(BaseModel):
    username: str
    password: str
    totp_code: str


class Setup2FAResponse(BaseModel):
    secret: str
    provisioning_uri: str


class Verify2FARequest(BaseModel):
    totp_code: str
