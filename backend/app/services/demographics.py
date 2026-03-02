"""
Author demographic inference.
- Gender: via gender_guesser (dictionary-based, no heavy deps)
- Ethnicity: US Census 2010 surname data (162K surnames, pickle at app/data/census_surnames.pkl)
  Falls back gracefully if the data file is missing.
  Returns the most probable racial/ethnic category for the last name, plus a confidence score.
"""
from __future__ import annotations
import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Gender inference
# ---------------------------------------------------------------------------

def infer_gender(full_name: str) -> Optional[str]:
    """
    Return 'male', 'female', 'mostly_male', 'mostly_female', or None.
    Uses the gender_guesser library (pure Python dictionary, no ML).
    """
    try:
        import gender_guesser.detector as gender
        d = gender.Detector(case_sensitive=False)
        first = full_name.strip().split()[0] if full_name.strip() else ""
        result = d.get_gender(first)
        if result in ("male", "female", "mostly_male", "mostly_female"):
            return result
        return None
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ethnicity inference — US Census 2010 Surname List (162K surnames)
# Pickle stores: { surname_lower: (pct_white, pct_black, pct_asian, pct_hispanic) }
# Source: https://www.census.gov/topics/population/genealogy/data/2010_surnames.html
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).parent.parent / "data" / "census_surnames.pkl"
_ETHNICITY_LABELS = ["white", "black", "asian", "hispanic"]


@lru_cache(maxsize=1)
def _load_surname_data() -> dict:
    """Load the Census surname lookup table (cached after first call)."""
    if not _DATA_PATH.exists():
        print(f"[demographics] WARNING: {_DATA_PATH} not found — ethnicity inference disabled")
        return {}
    try:
        with open(_DATA_PATH, "rb") as f:
            data = pickle.load(f)
        print(f"[demographics] Loaded {len(data):,} Census surnames from {_DATA_PATH}")
        return data
    except Exception as e:
        print(f"[demographics] ERROR loading Census data: {e}")
        return {}


def _last_name(full_name: str) -> str:
    """Extract last name from full name."""
    parts = full_name.strip().split()
    return parts[-1].lower() if parts else ""


def infer_ethnicity(full_name: str) -> Optional[str]:
    """
    Return most probable ethnicity label for a name.
    Uses US Census 2010 surname frequency data (162K surnames).
    Returns one of: 'white', 'black', 'asian', 'hispanic', or None if not found.
    """
    last = _last_name(full_name)
    if not last:
        return None
    data = _load_surname_data()
    row = data.get(last)
    if row is None:
        return None
    idx = row.index(max(row))
    return _ETHNICITY_LABELS[idx]


def infer_ethnicity_with_confidence(full_name: str) -> tuple[Optional[str], float]:
    """
    Return (ethnicity, confidence) where confidence is the dominant group's
    percentage divided by 100. E.g. ('hispanic', 0.93) for 'Garcia'.
    Returns (None, 0.0) if surname not found.
    """
    last = _last_name(full_name)
    if not last:
        return None, 0.0
    data = _load_surname_data()
    row = data.get(last)
    if row is None:
        return None, 0.0
    max_pct = max(row)
    idx = row.index(max_pct)
    return _ETHNICITY_LABELS[idx], round(max_pct / 100.0, 3)


# ---------------------------------------------------------------------------
# Convenience: infer both at once
# ---------------------------------------------------------------------------

def infer_demographics(full_name: str) -> dict:
    """Return {'gender': ..., 'ethnicity': ..., 'ethnicity_confidence': ...} for a full name."""
    ethnicity, confidence = infer_ethnicity_with_confidence(full_name)
    return {
        "gender": infer_gender(full_name),
        "ethnicity": ethnicity,
        "ethnicity_confidence": confidence,
    }
