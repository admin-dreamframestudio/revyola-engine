from fastapi import APIRouter, UploadFile, File, HTTPException

from app.schemas.rcm_ingestion import RCMIngestionResponse, RCMParseResponse
from app.services.era835.parser import parse_835_stub, parse_stored_835_stub

router = APIRouter(prefix="/api/v1/rcm", tags=["RCM"])


@router.get("/health")
def rcm_health():
    return {"status": "rcm module ready"}


@router.post("/ingestion/upload", response_model=RCMIngestionResponse)
async def upload_835(file: UploadFile = File(...)):
    try:
        content = await file.read()

        parsed = parse_835_stub(
            filename=file.filename or "unknown.835",
            content_type=file.content_type,
            content=content,
        )

        return RCMIngestionResponse(
            upload_id=parsed.upload_id,
            filename=parsed.filename,
            content_type=parsed.content_type,
            size_bytes=parsed.size_bytes,
            parser_status=parsed.parser_status,
            message=parsed.message,
            stored_path=parsed.stored_path,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ingestion/{upload_id}/parse", response_model=RCMParseResponse)
def parse_835(upload_id: str):
    try:
        parsed = parse_stored_835_stub(upload_id)

        return RCMParseResponse(
            upload_id=parsed.upload_id,
            filename=parsed.filename,
            parser_status=parsed.parser_status,
            file_size_bytes=parsed.file_size_bytes,
            claim_count=parsed.claim_count,
            line_count=parsed.line_count,
            adjustment_count=parsed.adjustment_count,
            claims_preview=parsed.claims_preview,
            actions_preview=parsed.actions_preview,
            work_queue=parsed.work_queue,
            suppression_feed=parsed.suppression_feed,
            message=parsed.message,
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))