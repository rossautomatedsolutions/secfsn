"""
Constants for SEC Financial Statement Navigator (secfsn)
"""

# ---------------------------------------------------------------------
# BASE URL for SEC Monthly / Quarterly Financial Statement datasets
# ---------------------------------------------------------------------
FSN_BASE_URL = "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets"

# Required User Agent (SEC requires identifying UA)
FSN_USER_AGENT = (
    "rossautomatedsolutions@gmail.com"   # <-- optional: replace email
)

# ---------------------------------------------------------------------
# Period definitions
# ---------------------------------------------------------------------

# Valid FSN quarters (1–4)
FSN_QUARTERS = [1, 2, 3, 4]

# Valid month list (used for monthly FSN releases)
FSN_MONTHS = list(range(1, 13))

# Tables present in FSN releases
TSV_TABLES = ["sub", "num", "pre", "tag", "txt"]

# Whether to include and convert the VERY large txt.tsv
INCLUDE_TXT_TABLE = False
