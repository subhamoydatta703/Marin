

from pydantic import BaseModel, ConfigDict
from typing import Literal


class Message(BaseModel):
    model_config = ConfigDict(strict=True)
    
    role:Literal["user", "model"]
    text:str

msgHistory: list[Message]=[]