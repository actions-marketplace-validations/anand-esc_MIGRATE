# shared/schemas.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

class ClassifiedFunction(BaseModel):
    """Output of Om's classifier — input to your converter."""
    function_id: str
    source_code: str
    classification: Literal["template_match", "llm_needed", "unsupported"]
    py2_constructs: list[str]     # e.g. ["print_stmt", "xrange", "dict_iteritems"]
    file_path: str = ""           # Added for CLI tracking
    lineno: int = 0               # Added for CLI tracking

class ConversionResult(BaseModel):
    """Output of your converter+critic — input to Pritam's verifier."""
    function_id: str
    converted_code: Optional[str] = None
    critic_verdict: Literal["clean", "leftover_py2_syntax", "signature_mismatch", "conversion_failed"]
    critic_notes: Optional[str] = None
    tokens_used: int = 0

# ---------------------------------------------------------------------------
# Pritam's verifier output (added for CLI)
# ---------------------------------------------------------------------------
class VerifierVerdict(str, Enum):
    EXACT_MATCH = "exact_match"
    CLEAR_MISMATCH = "clear_mismatch"
    AMBIGUOUS = "ambiguous"

class VerificationResult(BaseModel):
    """Return value of Pritam's sandbox-diff verifier for one function."""
    function_name: str
    verdict: VerifierVerdict
    details: Optional[str] = Field(
        default=None, description="Diff summary / fixture that triggered a mismatch"
    )
    fixture_count: Optional[int] = None

# ---------------------------------------------------------------------------
# Agent D's own pipeline-level status, used for build/summary.json.
# ---------------------------------------------------------------------------
class PipelineStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"

class FunctionOutcome(BaseModel):
    function_name: str
    file_path: str
    classification: str
    status: PipelineStatus
    critic_verdict: Optional[str] = None
    verifier_verdict: Optional[VerifierVerdict] = None
    detail: Optional[str] = None
