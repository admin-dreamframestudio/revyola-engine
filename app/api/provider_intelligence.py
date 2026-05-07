from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import httpx
import os
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("Arial", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

router = APIRouter(prefix="/api/provider-intelligence", tags=["Provider Intelligence"])

CMS_DATASET_ID = os.getenv(
    "CMS_PROVIDER_SERVICE_DATASET_ID",
    "92396110-2aed-4d63-a6a2-5d6207d46a29"
)

CMS_BASE_URL = f"https://data.cms.gov/data-api/v1/dataset/{CMS_DATASET_ID}/data"

COMMERCIAL_MULTIPLIER = 1.5
LEAKAGE_RATE = 0.12

REVYOLA_LOGO_URL = "https://lh3.googleusercontent.com/u/0/d/1g0QkO-1-uEbYpEP2XosAcvtnYYgcD-Y8"
QR_CODE_URL = "https://lh3.googleusercontent.com/u/0/d/1zXRAukzd3YJZdBMAEf3HRBJ8Tf4GlKNl"


class DiagnosticRow(BaseModel):
    hcpcs_code: str
    description: str
    number_of_services: float
    average_medicare_allowed_amount: float
    total_commercial_exposure: float
    annual_leakage: float


class ProviderDiagnosticResponse(BaseModel):
    npi: str
    provider_name: str
    specialty: Optional[str]
    location: Optional[str]
    commercial_multiplier: float
    leakage_rate: float
    total_commercial_exposure: float
    total_annual_leakage: float
    rows: List[DiagnosticRow]
    summary: str


def money(value: float) -> float:
    return round(float(value or 0), 2)


def fmt_money(value: float) -> str:
    return f"${value:,.2f}"


def clean_key(key: str) -> str:
    return (
        key.lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
        .replace("(", "")
        .replace(")", "")
    )


def get_value(row: Dict[str, Any], keys: List[str], default: Any = None):
    normalized = {clean_key(k): v for k, v in row.items()}

    for key in keys:
        if key in row and row[key] not in [None, ""]:
            return row[key]

        cleaned = clean_key(key)
        if cleaned in normalized and normalized[cleaned] not in [None, ""]:
            return normalized[cleaned]

    return default


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except Exception:
        return 0.0


async def fetch_image(url: str):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url)
        response.raise_for_status()
        return BytesIO(response.content)


def normalize_provider_name(row: Dict[str, Any]) -> str:
    first = get_value(row, [
        "Rndrng_Prvdr_First_Name",
        "Rendering Provider First Name",
        "First Name",
    ], "")

    last = get_value(row, [
        "Rndrng_Prvdr_Last_Org_Name",
        "Rendering Provider Last Name or Organization Name",
        "Last Name/Organization Name",
        "Provider Last Name/Organization Name",
    ], "")

    org = get_value(row, [
        "Rndrng_Prvdr_Org_Name",
        "Rendering Provider Organization Name",
        "Organization Name",
    ], "")

    if org:
        return str(org).strip()

    return f"{first} {last}".strip() or "Unknown Provider"


def normalize_location(row: Dict[str, Any]) -> str:
    city = get_value(row, [
        "Rndrng_Prvdr_City",
        "Rendering Provider City",
        "City",
    ], "")

    state = get_value(row, [
        "Rndrng_Prvdr_State_Abrvtn",
        "Rendering Provider State",
        "State",
    ], "")

    return ", ".join([x for x in [city, state] if x]) or "Unknown Location"


@router.get("/npi/{npi}/diagnostic", response_model=ProviderDiagnosticResponse)
async def get_npi_diagnostic(npi: str, size: int = 100, offset: int = 0):
    if not npi.isdigit() or len(npi) != 10:
        raise HTTPException(status_code=400, detail="NPI must be a 10-digit number.")

    params = {
        "filter[Rndrng_NPI]": npi,
        "size": size,
        "offset": offset,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(CMS_BASE_URL, params=params)
            response.raise_for_status()
            cms_rows = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"CMS API request failed: {str(exc)}")

    if not cms_rows:
        raise HTTPException(status_code=404, detail="No CMS service records found for this NPI.")

    first_row = cms_rows[0]

    provider_name = normalize_provider_name(first_row)

    specialty = get_value(first_row, [
        "Rndrng_Prvdr_Type",
        "Rendering Provider Type",
        "Provider Type",
        "Specialty",
    ], "Unknown Specialty")

    location = normalize_location(first_row)

    diagnostic_rows: List[DiagnosticRow] = []
    total_exposure = 0.0
    total_leakage = 0.0

    for row in cms_rows:
        hcpcs_code = str(get_value(row, [
            "HCPCS_Cd",
            "HCPCS Code",
            "HCPCS",
            "hcpcs_cd",
            "hcpcs_code",
        ], "")).strip()

        description = str(get_value(row, [
            "HCPCS_Desc",
            "HCPCS Description",
            "Description",
            "Service Description",
            "hcpcs_desc",
        ], "No description")).strip()

        number_of_services = as_float(get_value(row, [
            "Tot_Srvcs",
            "Total Services",
            "Number of Services",
            "Services",
            "tot_srvcs",
            "number_of_services",
        ], 0))

        avg_allowed = as_float(get_value(row, [
            "Avg_Mdcr_Alowd_Amt",
            "Average Medicare Allowed Amount",
            "Avg Medicare Allowed Amount",
            "Medicare Allowed Amount",
            "avg_mdcr_alowd_amt",
            "average_medicare_allowed_amount",
        ], 0))

        if not hcpcs_code or number_of_services <= 0 or avg_allowed <= 0:
            continue

        commercial_exposure = number_of_services * COMMERCIAL_MULTIPLIER * avg_allowed
        annual_leakage = commercial_exposure * LEAKAGE_RATE

        total_exposure += commercial_exposure
        total_leakage += annual_leakage

        diagnostic_rows.append(
            DiagnosticRow(
                hcpcs_code=hcpcs_code,
                description=description,
                number_of_services=number_of_services,
                average_medicare_allowed_amount=money(avg_allowed),
                total_commercial_exposure=money(commercial_exposure),
                annual_leakage=money(annual_leakage),
            )
        )

    diagnostic_rows = sorted(
        diagnostic_rows,
        key=lambda x: x.annual_leakage,
        reverse=True
    )

    return ProviderDiagnosticResponse(
        npi=npi,
        provider_name=provider_name,
        specialty=specialty,
        location=location,
        commercial_multiplier=COMMERCIAL_MULTIPLIER,
        leakage_rate=LEAKAGE_RATE,
        total_commercial_exposure=money(total_exposure),
        total_annual_leakage=money(total_leakage),
        rows=diagnostic_rows,
        summary=f'The total identified annual "Found Money" for this location is ${total_leakage:,.2f}.',
    )


@router.get("/npi/{npi}/diagnostic/pdf")
async def get_npi_diagnostic_pdf(npi: str, download: bool = False):
    diagnostic = await get_npi_diagnostic(npi=npi, size=100, offset=0)

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=24,
        leftMargin=24,
        topMargin=18,
        bottomMargin=14,
    )

    styles = getSampleStyleSheet()
    midnight = colors.HexColor("#0f172a")
    navy = midnight
    gold = colors.HexColor("#b48939")
    gold_accent = colors.HexColor("#b48939")
    red = colors.HexColor("#ea580c")
    alert_orange = colors.HexColor("#fb923c")
    gray = colors.HexColor("#000000")
    pure_black = colors.HexColor("#000000")
    light_gray = colors.HexColor("#f8fafc")
    border = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
    "ReportTitle",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=20,
    textColor=midnight,
    leading=24,
    spaceAfter=12,
    )   

    small_style = ParagraphStyle(
    "Small",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    textColor=pure_black,
    leading=13,
    )

    intro_style = ParagraphStyle(
    "Intro",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=10,
    textColor=pure_black,
    leading=15,
    spaceAfter=14,
    )

    white_label = ParagraphStyle(
    "WhiteLabel",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    textColor=colors.white,
    leading=10,
    alignment=1,
    )

    story = []

    try:
        logo_buffer = await fetch_image(REVYOLA_LOGO_URL)
        logo = Image(logo_buffer, width=52, height=52)
    except Exception:
        logo = Paragraph("", styles["Normal"])

    logo_text = Paragraph(
        "<b>REVYOLA</b><br/><font size='8' color='#c5a059'>REVENUE INTELLIGENCE</font>",
        ParagraphStyle(
            "LogoText",
            parent=styles["Normal"],
            fontName="Arial-Bold",
            fontSize=18,
            textColor=navy,
            leading=16,
        ),
    )

    logo_block = Table([[logo, logo_text]], colWidths=[60, 222])
    logo_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    provider_meta = Paragraph(
        f"<b>PROVIDER: {diagnostic.provider_name.upper()}</b><br/>"
        f"<b>NPI: {diagnostic.npi}</b><br/>"
        f"Specialty: {diagnostic.specialty}<br/>"
        f"Location: {diagnostic.location}",
        small_style,
    )

    header = Table([[logo_block, provider_meta]], colWidths=[330, 180])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, border),
    ]))

    story.append(header)
    story.append(Spacer(1, 10))

    story.append(Paragraph("EXECUTIVE REVENUE LEAKAGE DIAGNOSTIC", title_style))

    story.append(Paragraph(
        "This audit utilizes <b>Public Payer Utilization Data</b> to establish a "
        "commercial revenue benchmark. It identifies potential capital currently held "
        "by commercial payers due to <b>untracked payer underpayments</b>"
        " and <b>multiple procedure payment reductions (MPPR)</b>.",
        intro_style,
    ))

    kpi_table = Table(
        [[
            Paragraph(
                f"<font size='22' color='#b48939'><b>${round(diagnostic.total_commercial_exposure):,}</b></font><br/><br/>"
                "<font color='#ffffff'>ESTIMATED BILLABLE BASELINE</font>",
                white_label,
            ),
            Paragraph(
                f"<font size='22' color='#fb923c'><b>${round(diagnostic.total_annual_leakage):,}</b></font><br/><br/>"
                "<font color='#ffffff'>UNRECOVERED REVENUE</font>",
                white_label,
            ),
            Paragraph(
                f"<font size='22' color='#b48939'><b>{int(diagnostic.leakage_rate * 100)}%</b></font><br/><br/>"
                "<font color='#ffffff'>PAYER ERROR RATE</font>",
                white_label,
            ),
        ]],
        colWidths=[170, 170, 170],
        rowHeights=[75],
    )


    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), midnight),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#1e293b")),
        ("BOX", (0, 0), (-1, -1), 1, midnight),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    story.append(kpi_table)
    story.append(Spacer(1, 20))

    desc_style = ParagraphStyle(
        "TableDesc",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=gray,
        leading=10,
    )

    header_left = ParagraphStyle(
        "HeaderLeft",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        textColor=navy,
        leading=9,
        alignment=0,
    )

    header_right = ParagraphStyle(
        "HeaderRight",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        textColor=navy,
        leading=9,
        alignment=2,
    )

    table_rows = [[
        Paragraph("HCPCS", header_left),
        Paragraph("SERVICE DESCRIPTION", header_left),
        Paragraph("EST. BILLABLE BASELINE", header_right),
        Paragraph("UNRECOVERED REVENUE", header_right),
    ]]

    for row in diagnostic.rows[:8]:
        table_rows.append([
            row.hcpcs_code,
            Paragraph(row.description, desc_style),
            fmt_money(row.total_commercial_exposure),
            fmt_money(row.annual_leakage),
        ])

    table_rows.append([
        Paragraph("<b>AGGREGATE</b>", desc_style),
        Paragraph('<b>TOTAL IDENTIFIED "FOUND MONEY"</b>', desc_style),
        fmt_money(diagnostic.total_commercial_exposure),
        fmt_money(diagnostic.total_annual_leakage),
    ])

    service_table = Table(table_rows, colWidths=[82, 208, 115, 115])
    service_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), light_gray),
        ("TEXTCOLOR", (0, 0), (-1, 0), navy),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, border),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, border),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff7ed")),
        ("TEXTCOLOR", (0, -1), (-1, -1), red),
        ("FONTNAME", (0, -1), (-1, -1), "Arial-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#fed7aa")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(service_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        '"Historical data indicates a consistent pattern of unrecovered contractual '
        'variances; Revyola&apos;s diagnostic framework is designed to isolate and '
        'remediate these deep-seated systemic inefficiencies."',
        ParagraphStyle(
            "Quote",
            parent=styles["Normal"],
            fontName="Arial-Bold",
            fontSize=9,
            textColor=navy,
            alignment=1,
            leading=13,
        ),
    ))

    story.append(Spacer(1, 18))

    disclaimer = (
        "<b>LEGAL DISCLAIMER & LIMITATION OF LIABILITY:</b> This report is a "
        '"Revenue Benchmark" generated using publicly available data from CMS. '
        "Revyola makes no representations or warranties regarding the accuracy of "
        "public datasets or their direct correlation to private commercial contracts. "
        "All calculations are mathematical estimates based on a standard 12% industry "
        "variance rate and are for informational purposes only. This diagnostic does "
        "not constitute financial, legal, or professional medical billing advice."
    )

    try:
        qr_buffer = await fetch_image(QR_CODE_URL)
        qr_image = Image(qr_buffer, width=82, height=82)
    except Exception:
        qr_image = Paragraph("", styles["Normal"])

    qr_text = Paragraph(
        "<b>SCAN FOR FREE<br/>DEEP-DIVE AUDIT</b>",
        ParagraphStyle(
            "QRText",
            parent=styles["Normal"],
            fontName="Arial-Bold",
            fontSize=7.5,
            textColor=navy,
            alignment=1,
            leading=9,
        ),
    )

    qr_block = Table([[qr_image], [qr_text]])
    qr_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))

    footer_table = Table(
        [[Paragraph(disclaimer, small_style), qr_block]],
        colWidths=[400, 100],
    )

    footer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("LINEABOVE", (0, 0), (-1, -1), 1, border),
    ]))

    story.append(footer_table)

    doc.build(story)

    pdf = buffer.getvalue()
    buffer.close()

    filename = f"revyola-npi-{npi}-revenue-benchmark.pdf"
    disposition = "attachment" if download else "inline"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"'
        },
    )