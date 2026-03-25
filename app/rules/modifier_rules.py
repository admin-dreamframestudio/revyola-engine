def apply_modifier_rules(row, expected_amount):
    modifier = str(row.get("modifier", "")).strip().upper()
    cpt = str(row.get("cpt_code", "")).strip()

    # Default response
    result = {
        "expected_amount": float(expected_amount) if expected_amount is not None else 0.0,
        "rule_applied": "base_contract",
        "rule_reason": "Base benchmark / cohort logic applied",
    }

    # Modifier 25: E/M with same-day significant, separately identifiable service
    if modifier == "25" and cpt.startswith("992"):
        result["rule_applied"] = "modifier_25_em"
        result["rule_reason"] = "E/M with modifier 25 should not be materially suppressed without context"
        return result

    # Modifier 51: multiple procedure reduction
    if modifier == "51":
        adjusted = round(result["expected_amount"] * 0.50, 2)
        result["expected_amount"] = adjusted
        result["rule_applied"] = "modifier_51_multiple_procedure"
        result["rule_reason"] = "Multiple procedure reduction logic applied"
        return result

    # Modifier 59: distinct procedural service
    if modifier == "59":
        result["rule_applied"] = "modifier_59_distinct_service"
        result["rule_reason"] = "Distinct procedural service modifier considered"
        return result

    # Modifier 26: professional component
    if modifier == "26":
        adjusted = round(result["expected_amount"] * 0.40, 2)
        result["expected_amount"] = adjusted
        result["rule_applied"] = "modifier_26_professional_component"
        result["rule_reason"] = "Professional component logic applied"
        return result

    # Modifier TC: technical component
    if modifier == "TC":
        adjusted = round(result["expected_amount"] * 0.60, 2)
        result["expected_amount"] = adjusted
        result["rule_applied"] = "modifier_tc_technical_component"
        result["rule_reason"] = "Technical component logic applied"
        return result

    return result