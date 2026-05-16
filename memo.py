# memo.py

def money(value):
    if value is None:
        return "N/A"
    try:
        return f"€{float(value):,.0f}"
    except Exception:
        return str(value)


def pct(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return str(value)


def num(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value)


def get_property_name(property_data):
    address = property_data.get("address")
    neighbourhood = property_data.get("neighbourhood")
    city = property_data.get("city") or "Barcelona"

    if address and neighbourhood:
        return f"{address}, {neighbourhood}, {city}"
    if address:
        return f"{address}, {city}"
    if neighbourhood:
        return f"{neighbourhood}, {city}"
    return city


def get_recommendation(score):
    verdict = score.get("verdict")
    score_value = score.get("score", 0)
    classification = score.get("classification")
    deal_killer = score.get("deal_killer")

    if deal_killer:
        return "REJECT"

    if verdict == "YES" and score_value >= 80:
        return "APPROVE FOR DUE DILIGENCE"

    if verdict == "CONDITIONAL YES" or score_value >= 65:
        return "PROCEED ONLY AFTER DUE DILIGENCE"

    if verdict == "WEAK" or 50 <= score_value < 65:
        return "MANUAL REVIEW ONLY"

    return "REJECT"


def generate_ic_memo(property_data: dict, economics: dict, score: dict):
    property_name = get_property_name(property_data)

    score_value = score.get("score", 0)
    verdict = score.get("verdict")
    classification = score.get("classification")
    deal_killer = score.get("deal_killer")
    flags = score.get("due_diligence_flags", [])

    recommendation = get_recommendation(score)

    gba = property_data.get("gba_m2")
    ceiling_height = property_data.get("ceiling_height")
    loading_access = property_data.get("loading_access")
    access_type = property_data.get("access_type")
    floor_level = property_data.get("floor_level")
    building_type = property_data.get("building_type")
    description = property_data.get("description")

    true_yield = economics.get("true_ebitda_yield")
    ebitda_yield = economics.get("ebitda_yield")
    true_payback = economics.get("true_payback_years")
    payback = economics.get("payback_years")

    if recommendation == "APPROVE FOR DUE DILIGENCE":
        tone_summary = (
            "This asset appears to be a strong candidate based on current underwriting. "
            "The deal should proceed to due diligence, but final approval should depend on confirming legal use, technical condition, loading access, and conversion costs."
        )
    elif recommendation == "PROCEED ONLY AFTER DUE DILIGENCE":
        tone_summary = (
            "This asset has some attractive features but should not be treated as approved. "
            "It requires further due diligence before any offer or commitment."
        )
    elif recommendation == "MANUAL REVIEW ONLY":
        tone_summary = (
            "This asset should not be treated as a top deal. "
            "It may only be worth manual review if the price can be renegotiated, missing information is confirmed, or the operating assumptions improve."
        )
    else:
        tone_summary = (
            "This asset does not meet the current TruTrastero investment threshold. "
            "It should be rejected unless a major change in price, access, layout, or economics is confirmed."
        )

    flags_text = ""
    if flags:
        flags_text = "\n".join([f"- {flag}" for flag in flags])
    else:
        flags_text = "- No major automatic due diligence flags were generated."

    return f"""
# INVESTMENT COMMITTEE MEMO

## TruTrastero Self-Storage Conversion Analysis

**Property:** {property_name}  
**Recommendation:** {recommendation}  
**Score:** {score_value}/100  
**Verdict:** {verdict}  
**Classification:** {classification}  
**Deal Killer:** {deal_killer or "None"}  

---

## 1. Executive Summary

{tone_summary}

The property has been reviewed as a potential self-storage conversion opportunity. The key decision should be based on whether the location, access, building format, and return profile justify conversion risk.

---

## 2. Key Property Information

| Metric | Value |
|---|---|
| GBA | {gba} m² |
| Asking Price | {money(property_data.get("asking_price"))} |
| Asking Rent / Month | {money(property_data.get("asking_rent_month"))} |
| Building Type | {building_type or "Not confirmed"} |
| Floor Level | {floor_level or "Not confirmed"} |
| Access Type | {access_type or "Not confirmed"} |
| Loading Access | {loading_access} |
| Ceiling Height | {ceiling_height if ceiling_height else "Not confirmed — contact agent for more information"} |

---

## 3. Location View

**Neighbourhood:** {property_data.get("neighbourhood") or "Not confirmed"}  
**City:** {property_data.get("city") or "Barcelona"}  

The location should be judged by residential density, customer convenience, parking/loading practicality, safety perception, and whether the area can support self-storage pricing.

If the property is in El Raval, it should receive extra manual review because safety perception, loading restrictions, and customer confidence may be weaker than in Eixample, Gràcia, Les Corts, or stronger residential submarkets.

---

## 4. Building And Technical View

The building is suitable only if the following items are confirmed:

- Ceiling height is sufficient for storage conversion.
- Loading access is practical for vans or customer move-ins.
- The floor layout does not rely on poor stair-only movement.
- Fire safety and licensing requirements are achievable.
- Conversion capex is realistic for the building age and condition.

Missing ceiling height should not automatically kill the deal, but it must remain a due diligence item. If the rest of the score is strong, the correct next action is to contact the agent for confirmation.

---

## 5. Economics

| Metric | Value |
|---|---|
| NRA | {num(economics.get("nra_m2"))} m² |
| Estimated Units | {economics.get("estimated_units")} |
| Monthly Revenue | {money(economics.get("monthly_revenue"))} |
| Annual Revenue | {money(economics.get("annual_revenue"))} |
| Annual OpEx | {money(economics.get("annual_opex"))} |
| EBITDA | {money(economics.get("ebitda"))} |
| EBITDA Margin | {pct(economics.get("margin"))} |
| EBITDA Yield | {pct(ebitda_yield)} |
| True EBITDA Yield | {pct(true_yield)} |
| Payback Years | {payback if payback is not None else "N/A"} |
| True Payback Years | {true_payback if true_payback is not None else "N/A"} |
| Conversion Capex | {money(economics.get("conversion_capex"))} |
| Total Investment | {money(economics.get("total_investment"))} |

The most important metric is the **true EBITDA yield**, because it includes both acquisition price and conversion capex. A deal can look acceptable on purchase price alone but become weak once full conversion cost is included.

---

## 6. Due Diligence Flags

{flags_text}

---

## 7. Final Decision

**Recommendation:** {recommendation}

This memo should be used as a first-pass screening tool only. The property should not move forward unless the missing operational and technical items are confirmed and the economics remain acceptable after realistic conversion costs.
""".strip()