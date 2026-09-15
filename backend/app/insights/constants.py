"""
Part C4 constants for the Yaadhum rules engine, plus Part J1's board-urgency
multiplier scale.

No magic numbers anywhere else in `app/insights`. Every rule/gate references
these names.
"""

# ---------------------------------------------------------------------------
# Carried unchanged from v2
# ---------------------------------------------------------------------------
MIN_QUESTIONS_PER_GROUP = 5          # Tier Gap, Complexity Gap, Integration Gap
MIN_QUESTIONS_VARIANT_RULE = 3       # Variant Weakness only
MIN_DISTINCT_VARIANTS = 3            # Coverage, all rules
MATERIALITY_PP = 15                  # Tier, Complexity, Integration
MATERIALITY_VARIANT_PP = 20          # Variant Weakness
SELF_GAP_MATERIAL_PP = 15            # Self-comparison, material band
SELF_GAP_PRONOUNCED_PP = 25          # Self-comparison, pronounced band
CHAPTER_BALANCE_BAND_PP = 10         # Tier Gap and self-comparison only
FLATNESS_BAND_PP = 10                # Diffuse Signal
MAX_QUESTION_SHARE_OF_TIER = 0.15    # All tier-based rules (15%)
VARIANT_DOMINANCE_MAX = 0.50         # Complexity Gap (50%)
MIN_D2_NOT_L3 = 2                    # Integration Gap
MIN_PARTIAL_CREDIT_Q = 5             # Diffuse Signal
DIFFUSE_PREVALENCE = 0.80            # Diffuse Signal (80%)
CLASS_WIDE_THRESHOLD = 0.60          # Class-wide promotion (60%)
MIN_CLASS_SIZE = 15                  # Class-wide promotion
MAX_ABSENCE_RATE = 0.20              # Class-wide confidence cap (20%)
CEILING_GUARD = 0.90                 # Self-comparison compression (90%)
FLOOR_GUARD = 0.10                   # Self-comparison compression (10%)
MAX_INSIGHTS_PER_BAND = 5            # Report assembly

# ---------------------------------------------------------------------------
# New in v3
# ---------------------------------------------------------------------------
REFERENCE_BAND_SIZE = 5              # Gap to Reference Band
MIN_REFERENCE_BAND = 3               # Gap to Reference Band
GAP_CONCENTRATION_PP = 0.60          # Gap to Reference Band (60%)
MIN_QUESTIONS_FOR_LOCALISATION = 5   # Gap to Reference Band
STUDENT_REGISTER_GAP_CAP = 0.50      # Gap to Reference Band, student register (50%)
MIN_CLASSES_FOR_SCHOOL = 3           # School-wide promotion
SCHOOL_WIDE_THRESHOLD = 0.60         # School-wide promotion (60%)

# ---------------------------------------------------------------------------
# Part J1: board-urgency multiplier scale
# ---------------------------------------------------------------------------
# Appearances in the last 4 years -> multiplier
BOARD_URGENCY_MULTIPLIER_BY_APPEARANCES = {
    4: 2.0,   # 4 of 4, very high
    3: 1.5,   # 3 of 4, high
    2: 1.2,   # 2 of 4, moderate
    1: 1.0,   # 1 of 4, low
    0: 1.0,   # 0 of 4, not observed
}
BOARD_URGENCY_FLOOR = 1.0            # 1.0 is a hard floor, never below it

# Priority-watch-list threshold: multiplier >= this AND observation < HIGH
PRIORITY_WATCH_MULTIPLIER_THRESHOLD = 1.5

# ---------------------------------------------------------------------------
# E10/E12 tiebreak note: priority sits at ordering position 4, marks_at_stake
# at position 4 within a confidence band as a tiebreak (G2).
# ---------------------------------------------------------------------------
