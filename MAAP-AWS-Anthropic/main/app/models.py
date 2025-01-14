from pydantic import BaseModel, Field

#Define Your Models Parameters
class ModelKwargs(BaseModel):
    temperature: float = Field(default=0.5, ge=0, le=1)
    max_tokens: int = Field(default=2048, ge=1, le=4096)
    top_p: float = Field(default=0.5, ge=0, le=1)
    top_k: int = Field(default=0, ge=0, le=500)
    stop_sequences: list = Field(["\n\nHuman"])