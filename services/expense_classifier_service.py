from pathlib import Path
from typing import Any
import re

import joblib


# ============================================================
# PATHS
# ============================================================

SERVICE_DIR = Path(__file__).resolve().parent

BASE_DIR = SERVICE_DIR.parent

MODEL_PATH = (
    BASE_DIR
    / "models"
    / "expense_subcategory_classifier.joblib"
)


# ============================================================
# CATEGORY MAPPING
# ============================================================

ESSENTIAL_SUBCATEGORIES = {
    "Food",
    "Rent",
    "Electricity",
    "Transportation",
    "School",
    "Medicine",
    "Bills",
}

NON_ESSENTIAL_SUBCATEGORIES = {
    "Entertainment",
    "Shopping",
    "Gaming",
    "Dining Out",
    "Travel",
    "Subscriptions",
    "Lifestyle",
}


# ============================================================
# LOW CONFIDENCE THRESHOLD
# ============================================================

ML_CONFIDENCE_THRESHOLD = 0.45


# ============================================================
# STRONG KEYWORD RULES
# ============================================================

# These rules are intentionally focused on obvious cases.
# The ML model will still handle more ambiguous expenses.

SCHOOL_STRONG_KEYWORDS = {
    "tuition",
    "tuition fee",
    "tuition fees",
    "school fee",
    "school fees",
    "registration fee",
    "registration fees",
    "enrollment fee",
    "enrolment fee",
    "matriculation",
    "student fee",
    "student fees",
    "laboratory fee",
    "laboratory fees",
    "miscellaneous fee",
    "miscellaneous fees",
    "assessment fee",
    "assessment fees",
}

# Common OCR mistakes / variants
SCHOOL_OCR_VARIANTS = {
    "tution",
    "tuiton",
    "tuitions",
    "rrgistration",
    "regstration",
    "registratlon",
    "miscellianeous",
    "miscelilaneous",
    "miscelaneous",
    "colege",
    "coliege",
}

SCHOOL_INSTITUTION_KEYWORDS = {
    "school",
    "college",
    "university",
    "academy",
    "institute",
    "campus",
    "elementary",
    "highschool",
    "high school",
}

SCHOOL_PAYMENT_KEYWORDS = {
    "registration",
    "tuition",
    "tution",
    "fee",
    "fees",
    "payment",
    "assessment",
    "miscellaneous",
    "miscelilaneous",
    "enrollment",
    "enrolment",
}


# ============================================================
# LOAD MODEL
# ============================================================

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Expense classifier model not found: {MODEL_PATH}"
    )

expense_classifier_model: Any = joblib.load(
    MODEL_PATH
)


# ============================================================
# CATEGORY HELPER
# ============================================================

def get_parent_category(
    subcategory: str
) -> str:

    if subcategory in ESSENTIAL_SUBCATEGORIES:
        return "Essential"

    if subcategory in NON_ESSENTIAL_SUBCATEGORIES:
        return "Non-Essential"

    return "Others"


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(
    text: str
) -> str:

    text = (
        text or ""
    ).strip().lower()

    # Normalize line breaks / repeated spaces.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


# ============================================================
# DEDUPLICATE INPUT PARTS
# ============================================================

def build_combined_text(
    product_name: str,
    note: str,
    ocr_text: str,
) -> str:

    raw_parts = [
        product_name,
        note,
        ocr_text,
    ]

    unique_parts = []
    seen = set()

    for raw_part in raw_parts:

        cleaned = (
            raw_part or ""
        ).strip()

        if not cleaned:
            continue

        normalized = normalize_text(
            cleaned
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        unique_parts.append(
            cleaned
        )

    return " ".join(
        unique_parts
    ).strip()


# ============================================================
# KEYWORD CHECK HELPER
# ============================================================

def contains_any(
    text: str,
    keywords: set[str],
) -> bool:

    return any(
        keyword in text
        for keyword in keywords
    )


# ============================================================
# RULE-BASED SCHOOL DETECTION
# ============================================================

def detect_school_expense(
    combined_text: str
) -> dict | None:

    text = normalize_text(
        combined_text
    )

    # --------------------------------------------------------
    # RULE 1:
    # Very strong direct school-payment terms.
    # --------------------------------------------------------

    strong_matches = [
        keyword
        for keyword in SCHOOL_STRONG_KEYWORDS
        if keyword in text
    ]

    if strong_matches:

        return {
            "category": "Essential",
            "subcategory": "School",
            "confidence": 0.98,
            "source": "RULE",
        }


    # --------------------------------------------------------
    # RULE 2:
    # OCR-corrupted school-payment keywords.
    # --------------------------------------------------------

    ocr_matches = [
        keyword
        for keyword in SCHOOL_OCR_VARIANTS
        if keyword in text
    ]

    if ocr_matches:

        return {
            "category": "Essential",
            "subcategory": "School",
            "confidence": 0.95,
            "source": "RULE",
        }


    # --------------------------------------------------------
    # RULE 3:
    # Institution + payment context.
    #
    # Example:
    #
    # "Don Jose Ecleo Memorial College"
    # +
    # "Registration"
    # +
    # "Tuition"
    #
    # --------------------------------------------------------

    has_school_context = (
        contains_any(
            text,
            SCHOOL_INSTITUTION_KEYWORDS,
        )
    )

    has_payment_context = (
        contains_any(
            text,
            SCHOOL_PAYMENT_KEYWORDS,
        )
    )

    if (
        has_school_context
        and
        has_payment_context
    ):

        return {
            "category": "Essential",
            "subcategory": "School",
            "confidence": 0.93,
            "source": "RULE",
        }


    return None


# ============================================================
# GENERATE TOP ALTERNATIVES
# ============================================================

def build_alternatives(
    probabilities,
    classes,
    limit: int = 3,
) -> list[dict]:

    top_indices = (
        probabilities
        .argsort()[-limit:][::-1]
    )

    alternatives = []

    for index in top_indices:

        subcategory = str(
            classes[index]
        )

        alternatives.append(
            {
                "category": get_parent_category(
                    subcategory
                ),
                "subcategory": subcategory,
                "confidence": float(
                    probabilities[index]
                ),
            }
        )

    return alternatives


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_expense(
    product_name: str = "",
    note: str = "",
    ocr_text: str = "",
) -> dict:

    # --------------------------------------------------------
    # CLEAN INPUT
    # --------------------------------------------------------

    product_name = (
        product_name or ""
    ).strip()

    note = (
        note or ""
    ).strip()

    ocr_text = (
        ocr_text or ""
    ).strip()


    combined_text = build_combined_text(
        product_name=product_name,
        note=note,
        ocr_text=ocr_text,
    )


    if not combined_text:

        raise ValueError(
            "At least one expense description is required."
        )


    # ========================================================
    # STEP 1:
    # STRONG RULE-BASED CLASSIFICATION
    # ========================================================

    rule_result = detect_school_expense(
        combined_text
    )


    if rule_result is not None:

        return {
            "category": rule_result[
                "category"
            ],
            "subcategory": rule_result[
                "subcategory"
            ],
            "confidence": rule_result[
                "confidence"
            ],
            "source": rule_result[
                "source"
            ],
            "inputText": combined_text,
            "alternatives": [
                {
                    "category": "Essential",
                    "subcategory": "School",
                    "confidence": rule_result[
                        "confidence"
                    ],
                }
            ],
        }


    # ========================================================
    # STEP 2:
    # MACHINE LEARNING PREDICTION
    # ========================================================

    probabilities = (
        expense_classifier_model
        .predict_proba(
            [combined_text]
        )[0]
    )

    classes = (
        expense_classifier_model
        .classes_
    )


    best_index = int(
        probabilities.argmax()
    )


    predicted_subcategory = str(
        classes[best_index]
    )


    confidence = float(
        probabilities[best_index]
    )


    predicted_category = (
        get_parent_category(
            predicted_subcategory
        )
    )


    # ========================================================
    # STEP 3:
    # TOP ALTERNATIVE PREDICTIONS
    # ========================================================

    alternatives = build_alternatives(
        probabilities=probabilities,
        classes=classes,
        limit=3,
    )


    # ========================================================
    # STEP 4:
    # LOW-CONFIDENCE HANDLING
    # ========================================================

    if confidence < ML_CONFIDENCE_THRESHOLD:

        return {
            "category": predicted_category,
            "subcategory": predicted_subcategory,
            "confidence": confidence,
            "source": "ML_LOW_CONFIDENCE",
            "inputText": combined_text,
            "alternatives": alternatives,
        }


    # ========================================================
    # NORMAL ML RESPONSE
    # ========================================================

    return {
        "category": predicted_category,
        "subcategory": predicted_subcategory,
        "confidence": confidence,
        "source": "ML",
        "inputText": combined_text,
        "alternatives": alternatives,
    }