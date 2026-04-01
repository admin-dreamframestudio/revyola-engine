from dataclasses import dataclass
from pathlib import Path
import uuid


ALLOWED_835_EXTENSIONS = {".835", ".txt", ".era"}
UPLOAD_DIR = Path("app/storage/uploads/835")


@dataclass
class Parsed835File:
    upload_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    parser_status: str
    message: str
    stored_path: str


@dataclass
class Parse835Summary:
    upload_id: str
    filename: str
    parser_status: str
    file_size_bytes: int
    claim_count: int
    line_count: int
    adjustment_count: int
    claims_preview: list[dict]
    actions_preview: list[dict]
    work_queue: list[dict]
    suppression_feed: list[dict]
    message: str


def validate_835_filename(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_835_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_835_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{ext}'. Allowed: {allowed}")


def save_uploaded_835(filename: str, content: bytes) -> tuple[str, str]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    upload_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower() or ".835"
    stored_name = f"{upload_id}{ext}"
    stored_path = UPLOAD_DIR / stored_name

    stored_path.write_bytes(content)

    return upload_id, str(stored_path)


def get_stored_file_path(upload_id: str) -> Path:
    matches = list(UPLOAD_DIR.glob(f"{upload_id}.*"))
    if not matches:
        raise FileNotFoundError(f"No uploaded file found for upload_id '{upload_id}'")
    return matches[0]


def normalize_edi_text(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="ignore").strip()
    text = text.replace("\n", "").replace("\r", "")
    return text


def split_edi_segments(edi_text: str) -> list[str]:
    return [segment.strip() for segment in edi_text.split("~") if segment.strip()]


def parse_clp_segment(segment: str) -> dict:
    parts = segment.split("*")
    return {
        "claim_id": parts[1] if len(parts) > 1 else "",
        "total_charge": float(parts[3]) if len(parts) > 3 and parts[3] else 0.0,
        "paid_amount": float(parts[4]) if len(parts) > 4 and parts[4] else 0.0,
        "patient_responsibility": float(parts[5]) if len(parts) > 5 and parts[5] else 0.0,
        "payer_claim_id": parts[7] if len(parts) > 7 else "",
    }


def parse_cas_segment(segment: str) -> dict:
    parts = segment.split("*")
    group_code = parts[1] if len(parts) > 1 else ""
    reason_code = parts[2] if len(parts) > 2 else ""
    amount = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0

    return {
        "group_code": group_code,
        "reason_code": reason_code,
        "adjustment_code": f"{group_code}-{reason_code}" if group_code and reason_code else "",
        "adjustment_amount": amount,
    }


def map_action(adjustment_code: str) -> tuple[str, str, str]:
    mapping = {
        "CO-16": (
            "work",
            "Missing or invalid information",
            "Correct missing information and prepare resubmission or appeal packet.",
        ),
        "CO-45": (
            "suppress",
            "Contractual adjustment",
            "Suppress from active collector work unless exception criteria apply.",
        ),
        "CO-97": (
            "suppress",
            "Bundled or included service",
            "Suppress unless modifier or coding review indicates rebill opportunity.",
        ),
        "PR-1": (
            "suppress",
            "Deductible responsibility",
            "Do not send to payer follow-up. Route to patient responsibility workflow if needed.",
        ),
    }

    return mapping.get(
        adjustment_code,
        (
            "work",
            "Unmapped adjustment code",
            "Review claim manually and determine next action.",
        ),
    )

def score_action(
    *,
    adjustment_code: str,
    adjustment_amount: float,
    action_type: str,
) -> int:
    # dollar weight: 0-40
    if adjustment_amount >= 5000:
        dollar_weight = 40
    elif adjustment_amount >= 2000:
        dollar_weight = 30
    elif adjustment_amount >= 750:
        dollar_weight = 20
    elif adjustment_amount >= 250:
        dollar_weight = 10
    else:
        dollar_weight = 5

    # denial/code weight: 0-35
    code_weights = {
        "CO-16": 30,
        "CO-22": 26,
        "CO-109": 32,
        "CO-96": 20,
        "CO-97": 8,
        "CO-45": 3,
        "PR-1": 1,
    }
    code_weight = code_weights.get(adjustment_code, 15)

    # action type weight: 0-25
    action_weight_map = {
        "work": 25,
        "prevent": 18,
        "suppress": 2,
    }
    action_weight = action_weight_map.get(action_type, 10)

    score = dollar_weight + code_weight + action_weight
    return max(0, min(100, score))

def parse_835_stub(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> Parsed835File:
    validate_835_filename(filename)
    upload_id, stored_path = save_uploaded_835(filename, content)

    return Parsed835File(
        upload_id=upload_id,
        filename=filename or "unknown.835",
        content_type=content_type,
        size_bytes=len(content),
        parser_status="stored",
        message="835 file accepted and stored. Real parsing not yet enabled.",
        stored_path=stored_path,
    )


def parse_stored_835_stub(upload_id: str) -> Parse835Summary:
    stored_path = get_stored_file_path(upload_id)
    content = stored_path.read_bytes()

    edi_text = normalize_edi_text(content)
    segments = split_edi_segments(edi_text)

    claim_segments = [s for s in segments if s.startswith("CLP")]
    svc_segments = [s for s in segments if s.startswith("SVC")]
    cas_segments = [s for s in segments if s.startswith("CAS")]

    claims_preview = []
    actions_preview = []

    current_claim_id = ""

    for segment in segments:
        if segment.startswith("CLP"):
            parsed_claim = parse_clp_segment(segment)
            current_claim_id = parsed_claim["claim_id"]
            claims_preview.append(parsed_claim)

        elif segment.startswith("CAS"):
            parsed_cas = parse_cas_segment(segment)
            action_type, reason, recommended_action = map_action(parsed_cas["adjustment_code"])

            priority_score = score_action(
                adjustment_code=parsed_cas["adjustment_code"],
                adjustment_amount=parsed_cas["adjustment_amount"],
                action_type=action_type,
            )

            actions_preview.append(
                {
                    "claim_id": current_claim_id,
                    "adjustment_code": parsed_cas["adjustment_code"],
                    "adjustment_amount": parsed_cas["adjustment_amount"],
                    "action_type": action_type,
                    "reason": reason,
                    "recommended_action": recommended_action,
                    "priority_score": priority_score,
                }
            )

    sorted_actions = sorted(
        actions_preview,
        key=lambda x: x["priority_score"],
        reverse=True,
    )

    work_queue = [a for a in sorted_actions if a["action_type"] == "work"]
    suppression_feed = [a for a in sorted_actions if a["action_type"] == "suppress"]

    return Parse835Summary(
        upload_id=upload_id,
        filename=stored_path.name,
        parser_status="parsed_claims_actions_and_queues",
        file_size_bytes=len(content),
        claim_count=len(claim_segments),
        line_count=len(svc_segments),
        adjustment_count=len(cas_segments),
        claims_preview=claims_preview[:20],
        actions_preview=sorted_actions[:50],
        work_queue=work_queue[:50],
        suppression_feed=suppression_feed[:50],
        message="CLP and CAS segments extracted into claim preview, work queue, and suppression feed.",
    )