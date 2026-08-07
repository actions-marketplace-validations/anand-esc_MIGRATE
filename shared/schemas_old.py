# shared/schemas.py
from pydantic import BaseModel
from typing import Literal

class ClassifiedFunction(BaseModel):
    """Output of Om's classifier — input to your converter."""
    function_id: str
    source_code: str
    classification: Literal["template_match", "llm_needed", "unsupported"]
    py2_constructs: list[str]     # e.g. ["print_stmt", "xrange", "dict_iteritems"]

class ConversionResult(BaseModel):
    """Output of your converter+critic — input to Pritam's verifier."""
    function_id: str
    converted_code: str
    critic_verdict: Literal["clean", "leftover_py2_syntax", "signature_mismatch", "conversion_failed"]
    critic_notes: str
    tokens_used: int
