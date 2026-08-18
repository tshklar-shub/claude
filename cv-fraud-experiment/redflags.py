"""
Reference list of CV/application-stage fraud indicators.

Originally grounded only in DPRK IT-worker fraud cases (DOJ indictments,
FBI/CISA advisories, KnowBe4's own incident writeup). Expanded to cover the
broader, more common categories of resume fraud documented by background-check
industry research (HireRight's 2025 Global Benchmark Report, SHRM), which
found education-credential discrepancies as the single most common issue
(47% of employers in EMEA) and identity fraud affecting 1 in 6 employers --
plus emerging patterns like "overemployment" (concealed concurrent full-time
roles) and resume-mill/facilitator-ring template reuse across candidates.

Used both to seed synthetic CV generation (so we know ground truth) and to
drive the scoring heuristic in score_cv.py / similarity_check.py.

Each entry: id, description, weight (relative severity, 1-10), category, and
the field(s) in the extraction schema it depends on.

Categories:
  identity_impersonation  - candidate isn't who/where they claim to be
  credential_fraud        - fabricated/unverifiable education or certs
  experience_fabrication  - invented, inflated, or overlapping work history
  reference_fraud         - unverifiable or planted references
  ai_generated_boilerplate - content that reads as templated/AI-boilerplate
  farm_template_reuse     - cross-candidate signal, not visible per-CV
"""

RED_FLAGS = [
    {
        "id": "sparse_recent_history",
        "description": "Work history is thin or only recently established (little to no verifiable history older than ~2 years)",
        "weight": 7,
        "category": "identity_impersonation",
        "fields": ["companies", "years_experience"],
    },
    {
        "id": "illogical_progression",
        "description": "Career progression doesn't add up (e.g. seniority jumps, overlapping roles, implausible titles for tenure)",
        "weight": 6,
        "category": "experience_fabrication",
        "fields": ["companies"],
    },
    {
        "id": "name_spelling_inconsistent",
        "description": "Candidate's own name is spelled/formatted inconsistently across the document",
        "weight": 8,
        "category": "identity_impersonation",
        "fields": ["full_name", "raw_text"],
    },
    {
        "id": "free_email_domain",
        "description": "Personal free-email provider (gmail/yahoo/outlook) used instead of any professional or institutional domain",
        "weight": 2,
        "category": "identity_impersonation",
        "fields": ["email_domain_type"],
    },
    {
        "id": "phone_format_suspicious",
        "description": "Phone number formatted in a way inconsistent with claimed country/region (e.g. VOIP-style formatting, mismatched area code vs claimed location)",
        "weight": 4,
        "category": "identity_impersonation",
        "fields": ["phone", "location_claimed"],
    },
    {
        "id": "thin_linkedin",
        "description": "LinkedIn URL missing, or present but implausibly sparse for stated years of experience",
        "weight": 5,
        "category": "identity_impersonation",
        "fields": ["linkedin_url", "years_experience"],
    },
    {
        "id": "thin_github",
        "description": "GitHub/portfolio missing or generic/templated for a claimed senior engineer",
        "weight": 3,
        "category": "experience_fabrication",
        "fields": ["github_url"],
    },
    {
        "id": "reference_personal_contact_only",
        "description": "References reachable only via personal cell/email, never an official company line",
        "weight": 5,
        "category": "reference_fraud",
        "fields": ["references"],
    },
    {
        "id": "address_implausible",
        "description": "Claimed address/location is vague, generic, or inconsistent with other location signals in the document",
        "weight": 4,
        "category": "identity_impersonation",
        "fields": ["location_claimed"],
    },
    {
        "id": "overly_polished_language",
        "description": "Language is unusually polished/generic in a way inconsistent with claimed background (reads as templated or AI-generated boilerplate)",
        "weight": 3,
        "category": "ai_generated_boilerplate",
        "fields": ["raw_text"],
    },
    {
        "id": "employment_gaps_unexplained",
        "description": "Unexplained multi-month gaps between listed roles",
        "weight": 4,
        "category": "experience_fabrication",
        "fields": ["employment_gaps"],
    },
    {
        "id": "high_job_turnover",
        "description": "Unusually high number of jobs in the last 5 years relative to seniority claimed",
        "weight": 3,
        "category": "experience_fabrication",
        "fields": ["jobs_last_5_years"],
    },
    {
        "id": "education_credential_implausible",
        "description": "Claimed institution/degree reads as an unaccredited or diploma-mill-style provider, or honors/GPA claims are inconsistent or unverifiable",
        "weight": 6,
        "category": "credential_fraud",
        "fields": ["education"],
    },
    {
        "id": "seniority_experience_mismatch",
        "description": "Claimed seniority/title level is inconsistent with the years of experience implied by graduation date (e.g. a 'Staff'/'Principal' title within ~2 years of graduating)",
        "weight": 6,
        "category": "credential_fraud",
        "fields": ["education", "companies", "years_experience"],
    },
    {
        "id": "overlapping_employment_dates",
        "description": "Two or more listed roles show overlapping full-time date ranges -- consistent with fabricated history or undisclosed concurrent ('overemployment') work",
        "weight": 6,
        "category": "experience_fabrication",
        "fields": ["companies"],
    },
    {
        "id": "single_unverifiable_reference",
        "description": "Only one reference is offered, or references are reachable only through channels that trace back to the candidate rather than an independent party",
        "weight": 4,
        "category": "reference_fraud",
        "fields": ["references"],
    },
    {
        "id": "unverifiable_company_shell",
        "description": "A listed employer has no identifying detail at all (no location, industry, or context) making it read as a possible shell or fabricated company",
        "weight": 5,
        "category": "experience_fabrication",
        "fields": ["companies"],
    },
    {
        "id": "template_reuse_across_candidates",
        "description": "CV text is highly similar to another candidate's CV already seen in this dataset -- consistent with a resume-mill or facilitator-ring template reused across multiple identities",
        "weight": 9,
        "category": "farm_template_reuse",
        "fields": ["raw_text", "cross_candidate"],
    },
]

RED_FLAG_IDS = [f["id"] for f in RED_FLAGS]

MAX_POSSIBLE_SCORE = sum(f["weight"] for f in RED_FLAGS)


def flags_by_id():
    return {f["id"]: f for f in RED_FLAGS}


def flags_by_category():
    out = {}
    for f in RED_FLAGS:
        out.setdefault(f["category"], []).append(f)
    return out
