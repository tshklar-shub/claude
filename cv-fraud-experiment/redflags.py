"""
Reference list of CV/application-stage fraud indicators, grounded in publicly
documented DPRK IT-worker fraud cases (DOJ indictments, FBI/CISA advisories,
KnowBe4's own incident writeup, and vendor research). Used both to seed
synthetic CV generation (so we know ground truth) and to drive the scoring
heuristic in score_cv.py.

Each entry: id, description, weight (relative severity, 1-10), and the field(s)
in the extraction schema it depends on.
"""

RED_FLAGS = [
    {
        "id": "sparse_recent_history",
        "description": "Work history is thin or only recently established (little to no verifiable history older than ~2 years)",
        "weight": 7,
        "fields": ["companies", "years_experience"],
    },
    {
        "id": "illogical_progression",
        "description": "Career progression doesn't add up (e.g. seniority jumps, overlapping roles, implausible titles for tenure)",
        "weight": 6,
        "fields": ["companies"],
    },
    {
        "id": "name_spelling_inconsistent",
        "description": "Candidate's own name is spelled/formatted inconsistently across the document",
        "weight": 8,
        "fields": ["full_name", "raw_text"],
    },
    {
        "id": "free_email_domain",
        "description": "Personal free-email provider (gmail/yahoo/outlook) used instead of any professional or institutional domain",
        "weight": 2,
        "fields": ["email_domain_type"],
    },
    {
        "id": "phone_format_suspicious",
        "description": "Phone number formatted in a way inconsistent with claimed country/region (e.g. VOIP-style formatting, mismatched area code vs claimed location)",
        "weight": 4,
        "fields": ["phone", "location_claimed"],
    },
    {
        "id": "thin_linkedin",
        "description": "LinkedIn URL missing, or present but implausibly sparse for stated years of experience",
        "weight": 5,
        "fields": ["linkedin_url", "years_experience"],
    },
    {
        "id": "thin_github",
        "description": "GitHub/portfolio missing or generic/templated for a claimed senior engineer",
        "weight": 3,
        "fields": ["github_url"],
    },
    {
        "id": "reference_personal_contact_only",
        "description": "References reachable only via personal cell/email, never an official company line",
        "weight": 5,
        "fields": ["references"],
    },
    {
        "id": "address_implausible",
        "description": "Claimed address/location is vague, generic, or inconsistent with other location signals in the document",
        "weight": 4,
        "fields": ["location_claimed"],
    },
    {
        "id": "overly_polished_language",
        "description": "Language is unusually polished/generic in a way inconsistent with claimed background (reads as templated or AI-generated boilerplate)",
        "weight": 3,
        "fields": ["raw_text"],
    },
    {
        "id": "employment_gaps_unexplained",
        "description": "Unexplained multi-month gaps between listed roles",
        "weight": 4,
        "fields": ["employment_gaps"],
    },
    {
        "id": "high_job_turnover",
        "description": "Unusually high number of jobs in the last 5 years relative to seniority claimed",
        "weight": 3,
        "fields": ["jobs_last_5_years"],
    },
]

RED_FLAG_IDS = [f["id"] for f in RED_FLAGS]

MAX_POSSIBLE_SCORE = sum(f["weight"] for f in RED_FLAGS)


def flags_by_id():
    return {f["id"]: f for f in RED_FLAGS}
