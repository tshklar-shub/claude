"""
Extract structured fields from raw CV text.

Uses local_llm_client (Ollama), not claude_client -- this module handles real
candidate CVs (via score_real_dataset.py), and that data must not leave the
machine it's running on. Do not switch this back to claude_client without
re-checking why local_llm_client was chosen here specifically -- see
CLAUDE.md and RUNBOOK_REAL_DATASET.md.
"""

from local_llm_client import complete_json

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

# JSON Schema mirroring SCHEMA_DESCRIPTION, passed to local_llm_client so Ollama
# constrains generation to this exact shape (e.g. a field typed "string" cannot come
# back as a list) instead of only relying on the prompt describing the shape.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "email": {"type": ["string", "null"]},
        "email_domain_type": {"type": ["string", "null"], "enum": ["personal_free", "company", "edu", "other", None]},
        "phone": {"type": ["string", "null"]},
        "location_claimed": {"type": ["string", "null"]},
        "linkedin_url": {"type": ["string", "null"]},
        "github_url": {"type": ["string", "null"]},
        "years_experience": {"type": ["number", "null"]},
        "companies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["name", "title", "start", "end"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "grad_year": {"type": "string"},
                },
                "required": ["institution", "degree", "grad_year"],
            },
        },
        "employment_gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "between": {"type": "array", "items": {"type": "string"}},
                    "months": {"type": "number"},
                },
                "required": ["between", "months"],
            },
        },
        "avg_tenure_months": {"type": ["number", "null"]},
        "jobs_last_5_years": {"type": ["number", "null"]},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "contact_type": {"type": "string",
                                      "enum": ["personal_cell", "personal_email", "company_line", "unspecified"]},
                },
                "required": ["name", "contact_type"],
            },
        },
        "name_spelling_variants_found": {"type": "array", "items": {"type": "string"}},
        "cv_length_estimate_pages": {"type": "number"},
        "notable_language_style": {"type": "string"},
    },
    # Every scalar field is required (as string-or-null), not just the obviously
    # present ones -- verified in practice that when a field is merely optional in
    # the schema, the model sometimes omits it from the output entirely (e.g.
    # dropping linkedin_url/github_url/email/phone even when clearly present in
    # the CV text) rather than either finding it or explicitly returning null.
    # Requiring the key forces an explicit answer either way.
    "required": ["full_name", "email", "email_domain_type", "phone", "location_claimed",
                 "linkedin_url", "github_url", "companies", "education", "references"],
}


def extract_fields(cv_text: str) -> dict:
    user = f"{SCHEMA_DESCRIPTION}\n\nCV TEXT:\n---\n{cv_text}\n---"
    # See local_llm_client.complete_json: generous headroom beyond just the JSON
    # size, since local models can emit preamble before the actual output. Passing
    # EXTRACTION_SCHEMA constrains the output shape at the token level.
    return complete_json(EXTRACTION_SYSTEM, user, max_tokens=4000, schema=EXTRACTION_SCHEMA)
