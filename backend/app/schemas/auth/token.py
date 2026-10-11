from pydantic import BaseModel, Field


class Token(BaseModel):
    """JSON payload containing access token."""

    access_token: str
    token_type: str = "bearer"


class NewPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
