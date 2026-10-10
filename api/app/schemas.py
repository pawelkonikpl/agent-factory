from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

NOTE_MAX_LENGTH = 500


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=NOTE_MAX_LENGTH)


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    created_at: datetime
