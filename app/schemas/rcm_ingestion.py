from pydantic import BaseModel


class RCMIngestionResponse(BaseModel):
    upload_id: str
    filename: str
    content_type: str | None = None
    size_bytes: int
    parser_status: str
    message: str
    stored_path: str


class ClaimPreview(BaseModel):
    claim_id: str
    total_charge: float
    paid_amount: float
    patient_responsibility: float
    payer_claim_id: str | None = None


class ActionPreview(BaseModel):
    claim_id: str
    adjustment_code: str
    adjustment_amount: float
    action_type: str
    reason: str
    recommended_action: str
    priority_score: int


class RCMParseResponse(BaseModel):
    upload_id: str
    filename: str
    parser_status: str
    file_size_bytes: int
    claim_count: int
    line_count: int
    adjustment_count: int
    claims_preview: list[ClaimPreview]
    actions_preview: list[ActionPreview]
    work_queue: list[ActionPreview]
    suppression_feed: list[ActionPreview]
    message: str