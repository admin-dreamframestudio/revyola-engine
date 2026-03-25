import pandas as pd

def detect_bundling_patterns(df):
    """
    Detects add-on / bundled CPT patterns within same patient + service_date + payer context.
    Returns list of pattern findings.
    """

    findings = []

    required_cols = ["patient_id", "service_date", "payer", "cpt_code"]
    for col in required_cols:
        if col not in df.columns:
            return []  # can't evaluate bundling without these

    grouped = df.groupby(["patient_id", "service_date", "payer"])

    for (patient_id, service_date, payer), group in grouped:
        cpts = set(group["cpt_code"].astype(str))

        # Actinic keratosis pattern: 17000 + 17003 (add-on series)
        if "17000" in cpts and "17003" in cpts:
            claim_ids = group[group["cpt_code"].isin(["17000", "17003"])]["claim_id"].astype(str).tolist()

            findings.append({
                "pattern_type": "actinic_add_on_series",
                "description": "17003 appears with 17000 and should be evaluated as add-on reimbursement context",
                "payer": payer,
                "claim_ids": claim_ids,
                "recommendation": "Validate add-on reimbursement logic for CPT 17003 under payer contract",
            })

        # Biopsy pattern: 11102 + 11103
        if "11102" in cpts and "11103" in cpts:
            claim_ids = group[group["cpt_code"].isin(["11102", "11103"])]["claim_id"].astype(str).tolist()

            findings.append({
                "pattern_type": "biopsy_add_on_series",
                "description": "11103 appears with primary biopsy code and should be reviewed for add-on underpayment",
                "payer": payer,
                "claim_ids": claim_ids,
                "recommendation": "Ensure add-on biopsy units are reimbursed per contract terms",
            })

        # Lesion destruction grouping: 17110 vs 17111 (size-based differentiation)
        if "17110" in cpts and "17111" in cpts:
            claim_ids = group[group["cpt_code"].isin(["17110", "17111"])]["claim_id"].astype(str).tolist()

            findings.append({
                "pattern_type": "lesion_size_variance",
                "description": "17110 and 17111 billed together; verify appropriate reimbursement based on lesion count/size",
                "payer": payer,
                "claim_ids": claim_ids,
                "recommendation": "Review documentation and payer policy for lesion-based differentiation",
            })

    return findings