from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import uuid

from app.data.benchmark import load_benchmark
from app.rules.modifier_rules import apply_modifier_rules
from app.rules.icd_rules import get_icd_explainability
from app.rules.bundling_rules import detect_bundling_patterns
from app.services.drift import detect_payer_drift

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cuddly-tribble-r4w9g6w4jjwgf5qrg-3000.app.github.dev",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "revyola-engine"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        df = pd.read_csv(file.file)
        benchmark_df = load_benchmark()

        required_columns = ["claim_id", "payer", "cpt_code", "allowed_amount"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            return {"error": f"Missing required columns: {', '.join(missing)}"}

        df["claim_id"] = df["claim_id"].fillna("").astype(str)
        df["payer"] = df["payer"].fillna("").astype(str).str.upper().str.strip()
        df["cpt_code"] = df["cpt_code"].fillna("").astype(str).str.strip()

        if "modifier" in df.columns:
            df["modifier"] = df["modifier"].fillna("").astype(str).str.upper().str.strip()
        else:
            df["modifier"] = ""

        if "place_of_service" in df.columns:
            df["place_of_service"] = df["place_of_service"].fillna("").astype(str).str.strip()
        else:
            df["place_of_service"] = "11"

        if "service_date" in df.columns:
            df["service_date"] = pd.to_datetime(df["service_date"], errors="coerce")
        else:
            df["service_date"] = pd.NaT

        if "primary_icd10" in df.columns:
            df["primary_icd10"] = df["primary_icd10"].fillna("").astype(str).str.upper().str.strip()
        else:
            df["primary_icd10"] = ""

        if "patient_id" in df.columns:
            df["patient_id"] = df["patient_id"].fillna("").astype(str)
        else:
            df["patient_id"] = ""

        df["allowed_amount"] = pd.to_numeric(df["allowed_amount"], errors="coerce")
        df = df.dropna(subset=["allowed_amount"])

        if len(df) == 0:
            return {"error": "No valid rows found after parsing allowed_amount."}

        df = df.merge(
            benchmark_df,
            on=["payer", "cpt_code", "modifier", "place_of_service"],
            how="left",
        )

        cohort_cols = ["payer", "cpt_code", "modifier", "place_of_service"]

        baseline = (
            df.groupby(cohort_cols)["allowed_amount"]
            .agg(["median", "mean", "count"])
            .reset_index()
            .rename(
                columns={
                    "median": "cohort_median",
                    "mean": "cohort_mean",
                    "count": "cohort_count",
                }
            )
        )

        df = df.merge(baseline, on=cohort_cols, how="left")

        fallback_cols = ["payer", "cpt_code"]
        fallback = (
            df.groupby(fallback_cols)["allowed_amount"]
            .agg(["median", "mean", "count"])
            .reset_index()
            .rename(
                columns={
                    "median": "fallback_median",
                    "mean": "fallback_mean",
                    "count": "fallback_count",
                }
            )
        )

        df = df.merge(fallback, on=fallback_cols, how="left")

        def get_expected_amount(row):
            if pd.notna(row.get("benchmark_amount")):
                return row["benchmark_amount"]
            if pd.notna(row.get("cohort_median")):
                return row["cohort_median"]
            if pd.notna(row.get("fallback_median")):
                return row["fallback_median"]
            return 0.0

        def get_confidence(row):
            if pd.notna(row.get("benchmark_amount")):
                return "High"
            if pd.notna(row.get("cohort_count")) and row["cohort_count"] >= 8:
                return "High"
            if pd.notna(row.get("cohort_count")) and row["cohort_count"] >= 3:
                return "Medium"
            return "Low"

        df["expected_amount"] = df.apply(get_expected_amount, axis=1)
        df["confidence"] = df.apply(get_confidence, axis=1)

        modifier_results = df.apply(
            lambda row: apply_modifier_rules(row, row["expected_amount"]),
            axis=1,
        )
        modifier_results = pd.DataFrame(modifier_results.tolist(), index=df.index)

        df["expected_amount"] = pd.to_numeric(
            modifier_results["expected_amount"], errors="coerce"
        ).fillna(0.0)
        df["rule_applied"] = modifier_results["rule_applied"].fillna("").astype(str)
        df["rule_reason"] = modifier_results["rule_reason"].fillna("").astype(str)

        icd_results = df.apply(get_icd_explainability, axis=1)
        icd_results = pd.DataFrame(icd_results.tolist(), index=df.index)

        df["icd_explainability"] = icd_results["icd_explainability"].fillna("").astype(str)
        df["icd_confidence_adjustment"] = icd_results["icd_confidence_adjustment"].fillna("").astype(str)

        df["expected_amount"] = pd.to_numeric(df["expected_amount"], errors="coerce")
        df["gap_amount"] = (df["expected_amount"] - df["allowed_amount"]).round(2)

        df["deviation_pct"] = (
            ((df["allowed_amount"] - df["expected_amount"]) / df["expected_amount"]) * 100
        ).round(2)

        df = df.replace([float("inf"), float("-inf")], pd.NA)

        df["is_flagged"] = (
            pd.to_numeric(df["gap_amount"], errors="coerce").fillna(0) > 5
        ) & (
            pd.to_numeric(df["deviation_pct"], errors="coerce").fillna(0) < -5
        )

        flagged = df[df["is_flagged"]].copy()

        total_claims = int(len(df))
        flagged_claims_count = int(len(flagged))
        potential_underpayment = float(
            round(pd.to_numeric(flagged["gap_amount"], errors="coerce").fillna(0).sum(), 2)
        )

        bundling_signals = detect_bundling_patterns(df)
        payer_drift = detect_payer_drift(df)

        if flagged_claims_count == 0:
            return {
                "run_id": str(uuid.uuid4()),
                "summary": {
                    "total_claims": total_claims,
                    "flagged_claims": 0,
                    "potential_underpayment": 0.0,
                    "top_payer": "N/A",
                    "top_cpt": "N/A",
                },
                "patterns": [],
                "flagged_claims": [],
                "bundling_signals": bundling_signals,
                "payer_drift": payer_drift,
            }

        flagged["pattern_key"] = (
            flagged["payer"].fillna("").astype(str)
            + "|"
            + flagged["cpt_code"].fillna("").astype(str)
            + "|"
            + flagged["modifier"].fillna("").astype(str)
            + "|"
            + flagged["place_of_service"].fillna("").astype(str)
        )

        def reason_for_row(row):
            modifier = str(row.get("modifier", "")).strip().upper()
            if modifier not in ["", "NAN", "NONE"]:
                return "Below cohort baseline with modifier context"
            return "Below payer/CPT expected reimbursement range"

        flagged["reason"] = flagged.apply(reason_for_row, axis=1)

        pattern_df = (
            flagged.groupby(["pattern_key", "payer", "cpt_code", "modifier", "place_of_service"])
            .agg(
                impact=("gap_amount", "sum"),
                affected_claims=("claim_id", "count"),
                avg_deviation_pct=("deviation_pct", "mean"),
                avg_expected=("expected_amount", "mean"),
            )
            .reset_index()
        )

        def pattern_confidence(row):
            if row["affected_claims"] >= 8:
                return "High"
            if row["affected_claims"] >= 4:
                return "Medium"
            return "Low"

        pattern_df["impact"] = pd.to_numeric(
            pattern_df["impact"], errors="coerce"
        ).fillna(0.0).round(2)
        pattern_df["avg_deviation_pct"] = pd.to_numeric(
            pattern_df["avg_deviation_pct"], errors="coerce"
        ).fillna(0.0).round(2)
        pattern_df["avg_expected"] = pd.to_numeric(
            pattern_df["avg_expected"], errors="coerce"
        ).fillna(0.0).round(2)
        pattern_df["confidence"] = pattern_df.apply(pattern_confidence, axis=1)

        pattern_df["description"] = pattern_df.apply(
            lambda row: f'{row["payer"]} underpaying CPT {row["cpt_code"]}'
            + (
                f' with modifier {row["modifier"]}'
                if str(row["modifier"]).strip().upper() not in ["", "NAN", "NONE"]
                else ""
            ),
            axis=1,
        )

        patterns = pattern_df.sort_values(by="impact", ascending=False).head(12).copy()
        patterns["pattern_id"] = [f"PTRN-{i+1:03d}" for i in range(len(patterns))]

        pattern_id_map = dict(zip(patterns["pattern_key"], patterns["pattern_id"]))
        flagged["pattern_id"] = flagged["pattern_key"].map(pattern_id_map)

        top_payer_series = flagged.groupby("payer")["gap_amount"].sum().sort_values(ascending=False)
        top_cpt_series = flagged.groupby("cpt_code")["gap_amount"].sum().sort_values(ascending=False)

        top_payer = str(top_payer_series.index[0]) if len(top_payer_series) > 0 else "N/A"
        top_cpt = str(top_cpt_series.index[0]) if len(top_cpt_series) > 0 else "N/A"

        pattern_records = []
        for _, row in patterns.iterrows():
            pattern_records.append(
                {
                    "pattern_id": str(row["pattern_id"]),
                    "description": str(row["description"]),
                    "payer": "" if pd.isna(row["payer"]) else str(row["payer"]),
                    "cpt_code": "" if pd.isna(row["cpt_code"]) else str(row["cpt_code"]),
                    "modifier": "" if pd.isna(row["modifier"]) else str(row["modifier"]),
                    "place_of_service": ""
                    if pd.isna(row["place_of_service"])
                    else str(row["place_of_service"]),
                    "impact": float(0.0 if pd.isna(row["impact"]) else row["impact"]),
                    "affected_claims": int(
                        0 if pd.isna(row["affected_claims"]) else row["affected_claims"]
                    ),
                    "avg_deviation_pct": float(
                        0.0 if pd.isna(row["avg_deviation_pct"]) else row["avg_deviation_pct"]
                    ),
                    "confidence": "" if pd.isna(row["confidence"]) else str(row["confidence"]),
                }
            )

        flagged_subset = flagged[
            [
                "claim_id",
                "payer",
                "cpt_code",
                "modifier",
                "place_of_service",
                "allowed_amount",
                "expected_amount",
                "gap_amount",
                "deviation_pct",
                "confidence",
                "reason",
                "rule_applied",
                "rule_reason",
                "icd_explainability",
                "icd_confidence_adjustment",
                "pattern_id",
            ]
        ].sort_values(by="gap_amount", ascending=False).head(100).copy()

        flagged_subset = flagged_subset.replace([float("inf"), float("-inf")], pd.NA)

        flagged_subset["claim_id"] = flagged_subset["claim_id"].fillna("").astype(str)
        flagged_subset["payer"] = flagged_subset["payer"].fillna("").astype(str)
        flagged_subset["cpt_code"] = flagged_subset["cpt_code"].fillna("").astype(str)
        flagged_subset["modifier"] = flagged_subset["modifier"].fillna("").astype(str)
        flagged_subset["place_of_service"] = flagged_subset["place_of_service"].fillna("").astype(str)
        flagged_subset["confidence"] = flagged_subset["confidence"].fillna("").astype(str)
        flagged_subset["reason"] = flagged_subset["reason"].fillna("").astype(str)
        flagged_subset["rule_applied"] = flagged_subset["rule_applied"].fillna("").astype(str)
        flagged_subset["rule_reason"] = flagged_subset["rule_reason"].fillna("").astype(str)
        flagged_subset["icd_explainability"] = flagged_subset["icd_explainability"].fillna("").astype(str)
        flagged_subset["icd_confidence_adjustment"] = flagged_subset["icd_confidence_adjustment"].fillna("").astype(str)
        flagged_subset["pattern_id"] = flagged_subset["pattern_id"].fillna("UNASSIGNED").astype(str)

        flagged_subset["allowed_amount"] = pd.to_numeric(
            flagged_subset["allowed_amount"], errors="coerce"
        ).fillna(0.0).astype(float)
        flagged_subset["expected_amount"] = pd.to_numeric(
            flagged_subset["expected_amount"], errors="coerce"
        ).fillna(0.0).astype(float)
        flagged_subset["gap_amount"] = pd.to_numeric(
            flagged_subset["gap_amount"], errors="coerce"
        ).fillna(0.0).astype(float)
        flagged_subset["deviation_pct"] = pd.to_numeric(
            flagged_subset["deviation_pct"], errors="coerce"
        ).fillna(0.0).astype(float)

        flagged_claims = flagged_subset.to_dict(orient="records")

        return {
            "run_id": str(uuid.uuid4()),
            "summary": {
                "total_claims": total_claims,
                "flagged_claims": flagged_claims_count,
                "potential_underpayment": potential_underpayment,
                "top_payer": top_payer,
                "top_cpt": top_cpt,
            },
            "patterns": pattern_records,
            "flagged_claims": flagged_claims,
            "bundling_signals": bundling_signals,
            "payer_drift": payer_drift,
        }

    except Exception as e:
        return {"error": str(e)}