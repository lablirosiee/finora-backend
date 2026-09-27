from pathlib import Path
from typing import Any

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

    # Give product name the strongest signal.
    text_parts = []

    if product_name:
        text_parts.append(product_name)

    if note:
        text_parts.append(note)

    if ocr_text:
        text_parts.append(ocr_text)

    combined_text = " ".join(
        text_parts
    ).strip()

    if not combined_text:
        raise ValueError(
            "At least one expense description is required."
        )

    # --------------------------------------------------------
    # MODEL PREDICTION
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TOP 3 PREDICTIONS
    # --------------------------------------------------------

    top_indices = (
        probabilities
        .argsort()[-3:][::-1]
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

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "category": predicted_category,
        "subcategory": predicted_subcategory,
        "confidence": confidence,
        "source": "ML",
        "inputText": combined_text,
        "alternatives": alternatives,
    }