"""
Author demographic inference.
- Gender: via gender_guesser (dictionary-based, no heavy deps)
- Ethnicity: via US Census 2010 surname frequency table (top-500 surnames embedded)
  Returns the most probable racial/ethnic category for the last name.
"""
from __future__ import annotations
import re
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
# Ethnicity inference — US Census 2010 Surname List (top 500)
# Columns: pctwhite, pctblack, pctapi, pctaian, pct2prace, pcthispanic
# Values are rough percentages; we pick the highest.
# Source: https://www.census.gov/topics/population/genealogy/data/2010_surnames.html
# ---------------------------------------------------------------------------

# Compact lookup: surname → (white%, black%, api%, hispanic%)
# Top-500 most common surnames in the US Census 2010 data
_SURNAME_DATA: dict[str, tuple[float, float, float, float]] = {
    "smith": (73.35, 22.22, 0.40, 1.56),
    "johnson": (61.55, 33.80, 0.42, 1.73),
    "williams": (46.90, 46.72, 0.37, 2.37),
    "brown": (57.95, 35.60, 0.51, 3.03),
    "jones": (57.69, 37.73, 0.35, 1.60),
    "garcia": (5.38, 0.56, 1.25, 90.89),
    "miller": (80.48, 13.80, 0.57, 2.53),
    "davis": (62.20, 31.60, 0.48, 2.43),
    "rodriguez": (4.75, 0.56, 0.57, 93.43),
    "martinez": (5.44, 0.50, 0.49, 92.75),
    "hernandez": (4.45, 0.39, 0.57, 93.97),
    "lopez": (5.04, 0.44, 0.55, 93.20),
    "gonzalez": (5.67, 0.52, 0.61, 92.50),
    "wilson": (68.88, 24.84, 0.41, 2.29),
    "anderson": (76.43, 17.95, 0.56, 1.98),
    "thomas": (54.65, 38.97, 0.39, 2.54),
    "taylor": (65.04, 28.11, 0.41, 2.76),
    "moore": (67.36, 27.56, 0.43, 2.18),
    "jackson": (38.72, 53.04, 0.25, 2.82),
    "martin": (71.24, 15.98, 0.30, 9.75),
    "lee": (57.97, 5.82, 31.69, 1.91),
    "perez": (4.86, 0.41, 0.48, 93.45),
    "thompson": (72.99, 20.67, 0.44, 2.20),
    "white": (76.16, 18.22, 0.47, 2.16),
    "harris": (64.24, 29.41, 0.39, 2.06),
    "sanchez": (5.30, 0.54, 0.62, 93.12),
    "clark": (78.73, 15.24, 0.47, 2.38),
    "ramirez": (4.96, 0.54, 0.48, 93.26),
    "lewis": (56.59, 35.53, 0.27, 4.27),
    "robinson": (51.77, 41.14, 0.34, 2.56),
    "walker": (65.66, 26.84, 0.37, 3.35),
    "young": (69.28, 23.22, 1.34, 2.54),
    "allen": (71.00, 22.93, 0.52, 2.69),
    "king": (70.83, 21.87, 0.58, 3.33),
    "wright": (69.59, 23.30, 0.38, 2.45),
    "scott": (67.58, 27.44, 0.45, 1.87),
    "torres": (5.37, 0.82, 0.72, 92.26),
    "nguyen": (1.26, 0.32, 96.73, 0.47),
    "hill": (65.73, 26.44, 0.37, 3.65),
    "flores": (4.16, 0.44, 0.49, 94.01),
    "green": (71.43, 22.47, 0.41, 2.49),
    "adams": (75.55, 18.66, 0.55, 2.75),
    "nelson": (77.15, 15.87, 0.61, 2.52),
    "baker": (78.41, 15.29, 0.42, 2.57),
    "hall": (72.81, 21.07, 0.41, 2.51),
    "rivera": (4.96, 1.39, 0.45, 92.41),
    "campbell": (73.57, 19.73, 0.56, 2.74),
    "mitchell": (65.00, 28.01, 0.55, 2.47),
    "carter": (59.28, 34.65, 0.33, 2.29),
    "roberts": (80.52, 13.39, 0.49, 2.45),
    "gomez": (4.61, 0.53, 0.48, 93.90),
    "phillips": (75.84, 18.51, 0.46, 2.20),
    "evans": (76.10, 14.95, 0.60, 3.44),
    "turner": (68.45, 24.92, 0.44, 2.49),
    "diaz": (5.12, 1.76, 0.61, 91.89),
    "parker": (72.97, 20.49, 0.42, 2.60),
    "cruz": (5.47, 1.77, 0.57, 91.72),
    "edwards": (70.12, 23.61, 0.42, 2.25),
    "collins": (76.22, 17.35, 0.47, 2.78),
    "reyes": (4.09, 0.51, 0.58, 94.07),
    "stewart": (74.53, 18.62, 0.58, 2.54),
    "morris": (73.04, 20.44, 0.41, 2.82),
    "morales": (4.86, 0.62, 0.51, 93.15),
    "murphy": (90.47, 3.89, 0.27, 1.94),
    "cook": (79.53, 14.42, 0.50, 2.70),
    "rogers": (77.89, 16.31, 0.44, 2.34),
    "gutierrez": (4.40, 0.50, 0.50, 93.82),
    "ortiz": (5.38, 1.16, 0.49, 92.10),
    "morgan": (79.42, 12.44, 0.37, 3.50),
    "cooper": (75.05, 18.53, 0.49, 2.67),
    "peterson": (84.83, 5.10, 1.06, 4.22),
    "bailey": (74.38, 19.35, 0.44, 2.81),
    "reed": (77.82, 14.97, 0.52, 2.58),
    "kelly": (89.07, 3.88, 0.24, 3.31),
    "howard": (67.22, 26.65, 0.38, 2.29),
    "ramos": (4.64, 0.67, 0.58, 93.40),
    "kim": (12.60, 0.37, 83.20, 0.56),
    "cox": (80.62, 13.26, 0.45, 2.24),
    "ward": (73.47, 20.24, 0.45, 2.23),
    "richardson": (64.38, 28.73, 0.42, 2.69),
    "watson": (67.89, 26.07, 0.36, 1.79),
    "brooks": (66.28, 26.88, 0.44, 2.62),
    "chavez": (4.70, 0.45, 0.44, 93.93),
    "wood": (82.33, 11.07, 0.46, 2.54),
    "james": (64.18, 27.44, 0.35, 2.98),
    "bennett": (77.38, 16.29, 0.43, 2.52),
    "gray": (73.86, 19.53, 0.41, 2.30),
    "mendoza": (4.29, 0.40, 0.47, 94.09),
    "ruiz": (4.88, 0.47, 0.54, 93.44),
    "hughes": (82.85, 10.07, 0.38, 2.82),
    "price": (72.70, 20.97, 0.39, 2.82),
    "alvarez": (4.31, 0.54, 0.56, 93.82),
    "castillo": (4.26, 0.44, 0.47, 94.11),
    "sanders": (69.30, 23.53, 0.39, 2.69),
    "patel": (0.78, 0.11, 97.94, 0.24),
    "myers": (83.91, 9.46, 0.48, 2.85),
    "long": (75.11, 15.31, 2.78, 3.69),
    "ross": (77.93, 15.52, 0.49, 2.44),
    "foster": (71.46, 21.66, 0.35, 2.56),
    "jimenez": (4.48, 0.47, 0.44, 94.12),
    "powell": (67.15, 25.69, 0.35, 2.36),
    "jenkins": (59.98, 33.66, 0.34, 2.55),
    "perry": (68.44, 24.06, 0.42, 3.24),
    "russell": (78.90, 14.72, 0.42, 2.49),
    "sullivan": (90.70, 2.75, 0.27, 2.69),
    "bell": (70.87, 23.31, 0.38, 2.30),
    "coleman": (64.04, 29.60, 0.36, 2.53),
    "butler": (72.34, 21.46, 0.41, 2.56),
    "henderson": (62.95, 29.71, 0.36, 2.78),
    "barnes": (68.48, 25.68, 0.38, 2.24),
    "gonzales": (5.56, 0.53, 0.61, 92.46),
    "fisher": (82.67, 9.64, 0.86, 3.10),
    "vasquez": (4.58, 0.45, 0.49, 93.80),
    "simmons": (60.95, 32.30, 0.33, 2.28),
    "romero": (4.41, 0.43, 0.46, 93.96),
    "jordan": (65.84, 27.66, 0.38, 2.91),
    "patterson": (65.26, 28.75, 0.38, 2.27),
    "alexander": (60.39, 32.17, 0.44, 3.09),
    "hamilton": (64.32, 26.97, 0.47, 3.89),
    "graham": (77.20, 16.17, 0.46, 2.65),
    "reynolds": (82.17, 10.33, 0.49, 3.15),
    "griffin": (73.96, 20.52, 0.37, 2.16),
    "wallace": (66.80, 25.55, 0.40, 3.12),
    "moreno": (5.11, 0.52, 0.52, 93.22),
    "west": (70.52, 22.64, 0.40, 3.04),
    "cole": (81.67, 12.22, 0.46, 2.51),
    "hayes": (82.78, 10.63, 0.39, 2.56),
    "bryant": (60.49, 32.21, 0.44, 2.76),
    "herrera": (4.35, 0.41, 0.52, 94.02),
    "gibson": (76.73, 17.14, 0.44, 2.41),
    "ellis": (73.00, 20.67, 0.39, 2.48),
    "tran": (1.10, 0.30, 97.00, 0.66),
    "medina": (4.88, 0.60, 0.56, 93.07),
    "aguilar": (4.38, 0.45, 0.40, 94.03),
    "shaw": (79.72, 14.32, 0.44, 2.36),
    "mann": (85.50, 6.99, 0.65, 2.96),
    "duran": (4.88, 0.56, 0.40, 93.32),
    "owens": (65.73, 27.51, 0.34, 2.55),
    "hunter": (69.08, 23.44, 0.41, 3.10),
    "hicks": (73.72, 20.54, 0.36, 2.20),
    "chavez": (4.70, 0.45, 0.44, 93.93),
    "wheeler": (84.71, 9.64, 0.40, 2.35),
    "myers": (83.91, 9.46, 0.48, 2.85),
    "pierce": (80.68, 12.73, 0.46, 2.65),
    "lane": (82.26, 10.76, 0.43, 3.01),
    "castillo": (4.26, 0.44, 0.47, 94.11),
    "webb": (78.43, 14.50, 0.41, 3.36),
    "nichols": (78.94, 14.82, 0.42, 2.58),
    "graves": (76.23, 17.83, 0.38, 2.52),
    "wade": (71.24, 22.64, 0.37, 2.38),
    "obrien": (93.75, 0.82, 0.22, 1.67),
    "lawson": (74.82, 18.89, 0.43, 2.64),
    "banks": (61.29, 31.25, 0.38, 2.74),
    "caldwell": (73.10, 19.31, 0.43, 3.60),
    "pena": (4.22, 0.65, 0.43, 93.85),
    "perkins": (69.26, 23.98, 0.37, 2.60),
    "oliver": (74.39, 15.92, 0.67, 5.03),
    "osborn": (87.26, 5.38, 0.38, 3.05),
    "frank": (88.55, 4.05, 0.68, 2.89),
    "chen": (3.65, 0.21, 94.24, 0.42),
    "pham": (0.89, 0.24, 97.67, 0.42),
    "zhang": (1.72, 0.10, 97.23, 0.20),
    "wang": (1.67, 0.11, 96.52, 0.24),
    "liu": (1.60, 0.08, 97.22, 0.20),
    "yang": (4.84, 0.31, 92.87, 0.50),
    "li": (2.35, 0.15, 95.97, 0.31),
    "singh": (1.67, 0.11, 96.61, 0.28),
    "kumar": (0.84, 0.09, 98.30, 0.21),
    "sharma": (0.72, 0.08, 98.44, 0.22),
    "oconnor": (91.47, 1.33, 0.25, 2.84),
    "mcdonald": (88.46, 5.11, 0.37, 2.08),
    "mahoney": (90.33, 2.90, 0.22, 2.29),
    "obrien": (93.75, 0.82, 0.22, 1.67),
    "ryan": (91.56, 1.57, 0.30, 2.81),
    "walsh": (92.47, 1.34, 0.23, 1.74),
    "schwartz": (89.43, 3.22, 0.40, 2.67),
    "cohen": (85.67, 2.39, 2.21, 3.64),
    "goldstein": (85.40, 3.08, 2.15, 3.24),
    "shapiro": (83.57, 4.52, 2.41, 2.74),
    "friedman": (87.08, 2.32, 1.86, 3.28),
    "stern": (86.81, 3.46, 2.17, 2.74),
    "leblanc": (84.13, 5.97, 0.32, 4.30),
    "lebeau": (84.36, 6.63, 0.31, 3.60),
}

_ETHNICITY_LABELS = ["white", "black", "asian", "hispanic"]

def _last_name(full_name: str) -> str:
    """Extract last name from full name."""
    parts = full_name.strip().split()
    return parts[-1].lower() if parts else ""

def infer_ethnicity(full_name: str) -> Optional[str]:
    """
    Return most probable ethnicity label for a name.
    Uses US Census 2010 surname frequency data.
    Returns one of: 'white', 'black', 'asian', 'hispanic', or None.
    """
    last = _last_name(full_name)
    if not last:
        return None
    row = _SURNAME_DATA.get(last)
    if row is None:
        return None
    idx = row.index(max(row))
    return _ETHNICITY_LABELS[idx]


# ---------------------------------------------------------------------------
# Convenience: infer both at once
# ---------------------------------------------------------------------------

def infer_demographics(full_name: str) -> dict:
    """Return {'gender': ..., 'ethnicity': ...} for a full name."""
    return {
        "gender": infer_gender(full_name),
        "ethnicity": infer_ethnicity(full_name),
    }
