"""
Deterministic, rule-based red-flag scorer -- no LLM call. Operates on fields
from rule_based_extract.py plus a cross-candidate similarity_check pass.
Used to tune weights/thresholds at scale (hundreds of candidates) without
needing an API key; extract_cv.py/score_cv.py (Claude-based) remain the
general-purpose path for real, arbitrarily-formatted CVs.
"""

import re

import similarity_check
from redflags import flags_by_id, MAX_POSSIBLE_SCORE

REFERENCE_YEAR = 2026

TITLE_LADDER = ["Junior Developer", "Software Engineer", "Senior Software Engineer",
                "Staff Software Engineer", "Principal Software Engineer"]

DIPLOMA_MILL_KEYWORDS = ["online university", "distance college", "online technical institute",
                          "national technical university", "pacific coast university"]
SHELL_KEYWORDS = ["global tech solutions", "apex digital group", "summit enterprise partners",
                   "vantage consulting llc", "prime innovations group", "continental business solutions"]
POLISHED_KEYWORDS = ["highly skilled", "results-driven", "passionate about delivering",
                      "consistently exceeding expectations", "measurable business impact",
                      "proven ability to deliver"]

BY_ID = flags_by_id()


def _ym(s):
    if s == "present":
        return (REFERENCE_YEAR, 12)
    try:
        y, m = s.split("-")
        return (int(y), int(m))
    except (ValueError, AttributeError):
        return None


def _months_between(a, b):
    if a is None or b is None:
        return None
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def score_fields(extracted: dict, raw_text: str) -> dict:
    matched = []
    companies = extracted.get("companies") or []
    spans = [(c["title"], _ym(c["start"]), _ym(c["end"])) for c in companies]

    # sparse_recent_history
    if len(companies) <= 1 and spans and spans[0][1] and (REFERENCE_YEAR - spans[0][1][0]) <= 2:
        matched.append("sparse_recent_history")

    # illogical_progression: reaches Staff/Principal within <2yrs total career span
    if spans:
        earliest_start = min(s[1] for s in spans if s[1])
        top_title_idx = max(TITLE_LADDER.index(s[0]) for s in spans if s[0] in TITLE_LADDER)
        total_months = _months_between(earliest_start, (REFERENCE_YEAR, 12))
        if top_title_idx >= 3 and total_months is not None and total_months < 24:
            matched.append("illogical_progression")

    # name_spelling_inconsistent: linkedin handle's surname doesn't contain the CV's actual surname
    full_name = extracted.get("full_name") or ""
    handle = extracted.get("linkedin_handle")
    if handle and " " in full_name:
        surname = full_name.split()[-1].lower()
        if surname not in handle.lower():
            matched.append("name_spelling_inconsistent")

    # free_email_domain
    if extracted.get("email_domain_type") == "personal_free":
        matched.append("free_email_domain")

    # phone_format_suspicious
    phone = extracted.get("phone") or ""
    location = extracted.get("location_claimed") or ""
    if location and not phone.strip().startswith("+1"):
        matched.append("phone_format_suspicious")

    # thin_linkedin
    if not extracted.get("linkedin_handle"):
        matched.append("thin_linkedin")

    # thin_github
    if not extracted.get("has_github"):
        matched.append("thin_github")

    # reference_personal_contact_only / single_unverifiable_reference
    ref_text = (extracted.get("references_text") or "").lower()
    if "personal cell" in ref_text and "personal email" in ref_text:
        matched.append("reference_personal_contact_only")
    elif "one reference available" in ref_text:
        matched.append("single_unverifiable_reference")

    # address_implausible: no comma in location (no city/state)
    if location and "," not in location:
        matched.append("address_implausible")

    # overly_polished_language
    summary = (extracted.get("summary_text") or "").lower()
    if any(kw in summary for kw in POLISHED_KEYWORDS):
        matched.append("overly_polished_language")

    # employment_gaps_unexplained: >=6mo gap between consecutive roles
    ordered = sorted([s for s in spans if s[1] and s[2]], key=lambda s: s[1])
    for i in range(len(ordered) - 1):
        gap = _months_between(ordered[i][2], ordered[i + 1][1])
        if gap is not None and gap >= 6:
            matched.append("employment_gaps_unexplained")
            break

    # high_job_turnover: >=4 roles starting within the last 5 years
    recent = [s for s in spans if s[1] and (REFERENCE_YEAR - s[1][0]) <= 5]
    if len(recent) >= 4:
        matched.append("high_job_turnover")

    # education_credential_implausible
    education = extracted.get("education") or []
    edu_text = " ".join(e.get("institution", "") for e in education).lower()
    if any(kw in edu_text for kw in DIPLOMA_MILL_KEYWORDS) or len(education) >= 2:
        matched.append("education_credential_implausible")

    # seniority_experience_mismatch: Staff/Principal title with grad year within last 2 years
    if education:
        try:
            grad_year = max(int(e["year"]) for e in education)
        except (ValueError, KeyError):
            grad_year = None
        top_title_idx = max((TITLE_LADDER.index(s[0]) for s in spans if s[0] in TITLE_LADDER), default=-1)
        if grad_year is not None and top_title_idx >= 3 and (REFERENCE_YEAR - grad_year) <= 2:
            matched.append("seniority_experience_mismatch")

    # overlapping_employment_dates: 2+ roles simultaneously marked "present"
    present_count = sum(1 for c in companies if c.get("end") == "present")
    if present_count >= 2:
        matched.append("overlapping_employment_dates")

    # unverifiable_company_shell
    company_names = " ".join(c.get("company", "") for c in companies).lower()
    if any(kw in company_names for kw in SHELL_KEYWORDS):
        matched.append("unverifiable_company_shell")

    return matched


def score_candidate(candidate_id: str, extracted: dict, raw_text: str, all_candidates: list) -> dict:
    matched = score_fields(extracted, raw_text)

    sim = similarity_check.check(candidate_id, raw_text, all_candidates)
    sim_note = ""
    if sim["flagged"]:
        matched.append("template_reuse_across_candidates")
        sim_note = f" [similarity_check] near-duplicate of {sim['most_similar_candidate']} (ratio={sim['similarity_ratio']:.2f})."

    raw_score = sum(BY_ID[f]["weight"] for f in matched)
    fraud_score = round(100 * raw_score / MAX_POSSIBLE_SCORE, 1)
    return {"matched_flags": matched, "fraud_score": fraud_score, "reasoning": sim_note.strip()}
