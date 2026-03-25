import pandas as pd

def detect_payer_drift(df):
    """
    Detect reimbursement drift over time by payer + CPT using service_date.
    Returns a list of payer drift records.
    """

    required_cols = ["payer", "cpt_code", "allowed_amount", "service_date"]
    for col in required_cols:
        if col not in df.columns:
            return []

    working_df = df.copy()
    working_df["service_date"] = pd.to_datetime(working_df["service_date"], errors="coerce")
    working_df = working_df.dropna(subset=["service_date", "allowed_amount"])

    if len(working_df) == 0:
        return []

    working_df["service_month"] = working_df["service_date"].dt.to_period("M").astype(str)

    drift_summary = (
        working_df.groupby(["payer", "cpt_code", "service_month"])["allowed_amount"]
        .median()
        .reset_index()
    )

    drift_records = []

    for (payer, cpt_code), group in drift_summary.groupby(["payer", "cpt_code"]):
        group = group.sort_values("service_month")

        if len(group) < 2:
            continue

        first = group.iloc[0]["allowed_amount"]
        last = group.iloc[-1]["allowed_amount"]

        if pd.isna(first) or pd.isna(last) or first == 0:
            continue

        pct_change = round(((last - first) / first) * 100, 2)

        if abs(pct_change) >= 3:
            trend = "downward" if pct_change < 0 else "upward"

            drift_records.append({
                "payer": str(payer),
                "cpt_code": str(cpt_code),
                "start_month": str(group.iloc[0]["service_month"]),
                "end_month": str(group.iloc[-1]["service_month"]),
                "pct_change": float(pct_change),
                "trend": trend,
                "description": f"{payer} reimbursement for CPT {cpt_code} moved {pct_change}% from {group.iloc[0]['service_month']} to {group.iloc[-1]['service_month']}",
            })

    return drift_records