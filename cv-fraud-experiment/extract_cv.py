"""Extract structured fields from raw CV text via the Claude API."""

from claude_client import complete_json

EXTRACTION_SYSTEM = """You extract structured fields from a candidate's CV/resume text for a hiring
pipeline. Be literal and evidence-based: only report what is actually present in the text, and use
null/empty values when information is absent or unclear rather than guessing. Output strict JSON only,
matching exactly the schema described by the user, with no commentary or markdown fencing."""

SCHEMA_DESCRIPTION = """
Return a single JSON object with these fields:

{
  "full_name": string,
  "email": string or null,
  "email_domain_type": "personal_free" | "company" | "edu" | "other" | null,
  "phone": string or null,
  "location_claimed": string or null,
  "linkedin_url": string or null,
  "github_url": string or null,
  "years_experience": number or null,
  "companies": [ { "name": string, "title": string, "start": string, "end": string } ],
  "education": [ { "institution": string, "degree": string, "grad_year": string } ],
  "employment_gaps": [ { "between": [string, string], "months": number } ],
  "avg_tenure_months": number or null,
  "jobs_last_5_years": number or null,
  "references": [ { "name": string, "contact_type": "personal_cell" | "personal_email" | "company_line" | "unspecified" } ],
  "name_spelling_variants_found": [string],
  "cv_length_estimate_pages": number,
  "notable_language_style": string
}
"""


def extract_fields(cv_text: str) -> dict:
    user = f"{SCHEMA_DESCRIPTION}\n\nCV TEXT:\n---\n{cv_text}\n---"
    # See score_cv.py comment: this model's internal reasoning eats into max_tokens
    # before producing output, so this needs headroom beyond just the JSON size.
    return complete_json(EXTRACTION_SYSTEM, user, max_tokens=4000)
