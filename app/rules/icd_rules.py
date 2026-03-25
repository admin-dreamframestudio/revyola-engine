def get_icd_explainability(row):
    icd = str(row.get("primary_icd10", "")).strip().upper()
    cpt = str(row.get("cpt_code", "")).strip()

    if cpt == "11102" and icd.startswith("D48"):
        return {
            "icd_explainability": "Biopsy code aligns with neoplasm-related diagnosis context",
            "icd_confidence_adjustment": "supportive",
        }

    if cpt.startswith("992") and icd == "":
        return {
            "icd_explainability": "Missing diagnosis context reduces explainability confidence",
            "icd_confidence_adjustment": "negative",
        }

    if cpt in ["17000", "17003"] and (icd.startswith("L57") or icd.startswith("D48")):
        return {
            "icd_explainability": "Lesion destruction code is clinically plausible for diagnosis context",
            "icd_confidence_adjustment": "supportive",
        }

    if cpt in ["17110", "17111"] and icd.startswith("B07"):
        return {
            "icd_explainability": "Benign lesion destruction aligns with wart-related diagnosis context",
            "icd_confidence_adjustment": "supportive",
        }

    if icd != "":
        return {
            "icd_explainability": "Diagnosis context reviewed",
            "icd_confidence_adjustment": "neutral",
        }

    return {
        "icd_explainability": "No diagnosis context provided",
        "icd_confidence_adjustment": "neutral",
    }