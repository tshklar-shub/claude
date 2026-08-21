"""
Hybrid scoring: ONE LLM call per candidate (extraction only, via extract_cv.py),
then deterministic Python for red-flag matching instead of a second LLM call.

Why: extraction genuinely needs an LLM's flexibility across arbitrary real CV
formats -- no way around that. But most red flags, once fields are extracted,
are pure logic (date-range math, string lookups, counting), not judgment. A
second LLM call for those doesn't just cost time, it's a real accuracy risk:
qwen3:8b was caught twice fabricating employment-date overlaps that a simple
date comparison gets right every time, and misjudging a present LinkedIn URL
as evidence of a "thin" profile. Doing these in code is faster AND more
reliable for the checks that are genuinely just logic.

Confidence tiers (be honest about which flags this is actually good at):

  HIGH   -- pure logic on structured/extracted fields (dates, counts, string
            lookups). At least as reliable as LLM scoring was, usually more so.
  MEDIUM -- depends on a free-text job-title -> seniority-level heuristic
            (TITLE_KEYWORDS below). Real titles vary more than any fixed
            mapping can fully cover ("Tech Lead", "Engineering Manager II").
  LOW    -- depends on a fixed keyword/pattern list matching against
            open-ended text (is this institution a diploma mill, does this
            company name look like a shell, does this summary read as AI
            boilerplate). A genuinely novel example outside the keyword list
            won't be caught. This is the real accuracy trade of skipping the
            second LLM call -- previously an LLM judged these with (imperfect
            but broader) semantic understanding; a keyword list is narrower
            but instant and won't hallucinate a false positive out of nothing.
"""

import re

import similarity_check
from redflags import flags_by_id, MAX_POSSIBLE_SCORE

REFERENCE_YEAR = 2026
REFERENCE_MONTH = 8

CONFIDENCE = {
    "sparse_recent_history": "HIGH", "employment_gaps_unexplained": "HIGH",
    "high_job_turnover": "HIGH", "overlapping_employment_dates": "HIGH",
    "free_email_domain": "HIGH", "phone_format_suspicious": "HIGH",
    "thin_linkedin": "HIGH", "thin_github": "HIGH",
    "reference_personal_contact_only": "HIGH", "single_unverifiable_reference": "HIGH",
    "address_implausible": "HIGH", "name_spelling_inconsistent": "HIGH",
    "illogical_progression": "MEDIUM", "seniority_experience_mismatch": "MEDIUM",
    "education_credential_implausible": "LOW", "unverifiable_company_shell": "LOW",
    "overly_polished_language": "LOW", "template_reuse_across_candidates": "HIGH",
}

# Rough free-text title -> seniority-level mapping. Deliberately conservative:
# unrecognized titles map to level 1 (mid) rather than guessing high or low.
TITLE_KEYWORDS = [
    (0, ["intern", "junior", "jr.", "entry level", "associate"]),
    (2, ["senior", "sr.", "lead ", " lead", "iii"]),
    (3, ["staff", "principal", "director", "vp", "vice president", "head of", "chief"]),
]


TECH_ROLE_KEYWORDS = ["engineer", "developer", "programmer", "architect", "software",
                       "data scientist", "devops", "sre", "backend", "frontend", "full stack",
                       "full-stack", "infrastructure engineer", "machine learning", "ml engineer"]


def _is_tech_role(spans) -> bool:
    return any(kw in (s.get("title") or "").lower() for s in spans for kw in TECH_ROLE_KEYWORDS)


def _title_level(title: str) -> int:
    t = (title or "").lower()
    for level, keywords in reversed(TITLE_KEYWORDS):
        if any(kw in t for kw in keywords):
            return level
    return 1  # mid-level default


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _parse_date(s) -> tuple:
    """Best-effort parse of free-text dates ('Jul 2019', 'March 2022', '07/2006',
    '2019', '2019-07', 'Present'/'Current'/'Now') into (year, month). Returns None if
    nothing recognizable is found -- callers must handle that, not assume success."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().lower()
    if s in ("present", "current", "now", "ongoing", "today"):
        return (REFERENCE_YEAR, REFERENCE_MONTH)
    m = re.match(r"^(\d{4})-(\d{1,2})$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)  # MM/YYYY -- common on real resumes
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(2)), int(m.group(1)))
    m = re.match(r"^([a-z]{3,9})\.?\s+(\d{4})$", s)
    if m:
        mon = MONTHS.get(m.group(1)[:3])
        if mon:
            return (int(m.group(2)), mon)
    m = re.search(r"(\d{4})", s)
    if m:
        return (int(m.group(1)), 1)  # year only -- assume January
    return None


def _is_imprecise_date(s) -> bool:
    """True if _parse_date would resolve this to a bare year via its January-default
    fallback rather than an actual month. Matters because that default is a real bias:
    two roles listing only years ('2022' -> '2023') look like a fabricated 12-month gap
    even when the true gap could be anywhere from 0 to 23 months. Verified on a real CV:
    'employment_gaps_unexplained' fired on exactly this pattern with no real basis."""
    if not s or not isinstance(s, str):
        return True
    s = s.strip().lower()
    if s in ("present", "current", "now", "ongoing", "today"):
        return False
    if re.match(r"^\d{4}-\d{1,2}$", s):
        return False
    m = re.match(r"^(\d{1,2})/\d{4}$", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return False
    if re.match(r"^[a-z]{3,9}\.?\s+\d{4}$", s):
        return False
    return True


def _months_between(a, b):
    if a is None or b is None:
        return None
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


DIPLOMA_MILL_KEYWORDS = ["online university", "distance college", "online technical institute",
                          "national technical university", "correspondence"]
SHELL_SUFFIXES = ["llc", "group", "solutions", "partners", "enterprises", "consulting"]
POLISHED_KEYWORDS = ["highly skilled", "results-driven", "results driven", "passionate about delivering",
                      "consistently exceeding expectations", "measurable business impact",
                      "proven ability to deliver", "dynamic professional", "go-getter", "synergy"]

BY_ID = flags_by_id()


def score_fields(extracted: dict, raw_text: str) -> tuple:
    """Returns (matched_flag_ids, evidence_by_flag dict)."""
    matched, evidence = [], {}

    def flag(fid, ev):
        # Idempotent: overlapping_employment_dates can find multiple overlapping
        # pairs in one candidate (verified in practice: a 4-role real resume
        # produced 4 separate calls) -- without this guard, `matched` gets the
        # same flag_id appended repeatedly and its weight gets summed multiple
        # times, silently inflating the score.
        if fid not in matched:
            matched.append(fid)
            evidence[fid] = ev

    companies = extracted.get("companies") or []
    spans = []
    for c in companies:
        start, end = _parse_date(c.get("start")), _parse_date(c.get("end"))
        spans.append({"title": c.get("title", ""), "name": c.get("name", ""), "start": start, "end": end,
                       "start_raw": c.get("start"), "end_raw": c.get("end")})
    dated = [s for s in spans if s["start"]]

    # sparse_recent_history
    if len(companies) <= 1 and dated and (REFERENCE_YEAR - dated[0]["start"][0]) <= 2:
        flag("sparse_recent_history", f"only 1 role, starts {dated[0]['start_raw']}")

    # illogical_progression: reaches senior/staff level within <2yrs of the earliest start
    if dated:
        earliest = min(s["start"] for s in dated)
        top_level = max((_title_level(s["title"]) for s in spans), default=0)
        span_months = _months_between(earliest, (REFERENCE_YEAR, REFERENCE_MONTH))
        if top_level >= 3 and span_months is not None and span_months < 24:
            flag("illogical_progression", f"reaches '{spans[-1]['title']}' within ~{span_months}mo of earliest role")

    # name_spelling_inconsistent -- extraction itself already flags variants it noticed
    variants = extracted.get("name_spelling_variants_found") or []
    if len(variants) >= 2:
        flag("name_spelling_inconsistent", f"variants found during extraction: {variants}")

    # free_email_domain
    if extracted.get("email_domain_type") == "personal_free":
        flag("free_email_domain", f"email: {extracted.get('email')}")

    # phone_format_suspicious: phone carries an EXPLICIT non-US country code while
    # location reads as US. Verified false positive on a real CV: a plain domestic
    # number written without any "+1" prefix ("669-252-5046", extremely common --
    # most Americans don't prefix their own country code) was flagged just for
    # lacking "+1", which was never real evidence of anything. Only an explicit "+"
    # followed by a non-"1" country code is actually suspicious; no "+" prefix at all
    # is normal, not evidence of a foreign number.
    phone = (extracted.get("phone") or "").strip()
    location = (extracted.get("location_claimed") or "").strip()
    us_signals = ["united states", "usa", "u.s.", ", ca", ", ny", ", tx", ", wa", ", il", ", ma", ", co", ", fl", ", ga"]
    looks_us = any(sig in location.lower() for sig in us_signals) or re.search(r",\s*[A-Z]{2}$", location)
    country_code = re.match(r"^\+(\d{1,3})", phone)
    if country_code and looks_us and country_code.group(1) != "1":
        flag("phone_format_suspicious", f"phone '{phone}' vs location '{location}'")

    # thin_linkedin / thin_github: presence check, gated on a detected tech-role
    # context. Verified against 15 real, non-software resumes (accountant, aviation,
    # agriculture, etc.) that these fired on 15/15 of them ungated -- 0 of those 15
    # even mention LinkedIn at all, so absence isn't evidence of anything for a
    # population where it was never a norm to include it. thin_github's own
    # description was always scoped to "a claimed senior engineer"; this makes that
    # scoping actually enforced instead of just documented.
    if _is_tech_role(spans):
        if not extracted.get("linkedin_url"):
            flag("thin_linkedin", "no linkedin_url extracted (tech role detected)")
        if not extracted.get("github_url"):
            flag("thin_github", "no github_url extracted (tech role detected)")

    # reference channel checks, from extraction's own contact_type classification
    references = extracted.get("references") or []
    contact_types = [r.get("contact_type") for r in references]
    if contact_types and all(ct in ("personal_cell", "personal_email") for ct in contact_types):
        flag("reference_personal_contact_only", f"references: {contact_types}")
    elif len(references) == 1 and contact_types[0] in ("personal_cell", "personal_email", "unspecified"):
        flag("single_unverifiable_reference", f"only 1 reference, contact_type={contact_types[0]}")

    # address_implausible: no comma (no city/state structure) or a bare "remote"/"united states"
    if location and "," not in location:
        flag("address_implausible", f"location: '{location}'")

    # overly_polished_language -- LOW confidence, fixed keyword list
    summary = (extracted.get("notable_language_style") or "") + " " + raw_text
    hit_kw = next((kw for kw in POLISHED_KEYWORDS if kw in summary.lower()), None)
    if hit_kw:
        flag("overly_polished_language", f"matched boilerplate phrase: '{hit_kw}'")

    # employment_gaps_unexplained: >=6mo gap between consecutive dated roles, with a
    # higher bar (18mo) when either boundary date is year-only -- see _is_imprecise_date.
    ordered = sorted([s for s in spans if s["start"] and s["end"]], key=lambda s: s["start"])
    for i in range(len(ordered) - 1):
        gap = _months_between(ordered[i]["end"], ordered[i + 1]["start"])
        if gap is None:
            continue
        imprecise = _is_imprecise_date(ordered[i]["end_raw"]) or _is_imprecise_date(ordered[i + 1]["start_raw"])
        threshold = 18 if imprecise else 6
        if gap >= threshold:
            note = " (year-only dates -- true gap could be smaller)" if imprecise else ""
            flag("employment_gaps_unexplained",
                 f"{gap}mo gap between '{ordered[i]['end_raw']}' and '{ordered[i+1]['start_raw']}'{note}")
            break

    # high_job_turnover: >=4 roles starting within the last 5 years
    recent = [s for s in dated if (REFERENCE_YEAR - s["start"][0]) <= 5]
    if len(recent) >= 4:
        flag("high_job_turnover", f"{len(recent)} roles started within the last 5 years")

    # education_credential_implausible -- LOW confidence, fixed keyword list
    education = extracted.get("education") or []
    edu_text = " ".join(e.get("institution", "") for e in education).lower()
    hit = next((kw for kw in DIPLOMA_MILL_KEYWORDS if kw in edu_text), None)
    if hit:
        flag("education_credential_implausible", f"institution name matches diploma-mill pattern: '{hit}'")
    elif len(education) >= 2 and any("certificate" in e.get("degree", "").lower() for e in education):
        flag("education_credential_implausible", "degree + same-institution certificate combo")

    # seniority_experience_mismatch: senior/staff+ level with grad year in the last 2 years
    if education:
        grad_years = [int(m.group()) for e in education if (m := re.search(r"\d{4}", str(e.get("grad_year", ""))))]
        if grad_years:
            grad_year = max(grad_years)
            top_level = max((_title_level(s["title"]) for s in spans), default=0)
            if top_level >= 3 and (REFERENCE_YEAR - grad_year) <= 2:
                flag("seniority_experience_mismatch", f"grad_year={grad_year}, top title level={top_level}")

    # overlapping_employment_dates -- pure date-range math, the exact check the LLM
    # got wrong twice in live testing. Doing this in code makes it provably correct.
    present_roles = [s for s in dated if s["end_raw"] and str(s["end_raw"]).strip().lower() in
                      ("present", "current", "now", "ongoing")]
    if len(present_roles) >= 2:
        flag("overlapping_employment_dates",
             f"{len(present_roles)} roles simultaneously marked ongoing: " +
             ", ".join(f"{s['name']} ({s['start_raw']}-{s['end_raw']})" for s in present_roles))
    else:
        for i in range(len(dated)):
            for j in range(i + 1, len(dated)):
                a, b = dated[i], dated[j]
                if a["end"] and b["start"] and a["start"] <= b["start"] < a["end"] and a["end"] != (REFERENCE_YEAR, REFERENCE_MONTH):
                    flag("overlapping_employment_dates",
                         f"'{a['name']}' ({a['start_raw']}-{a['end_raw']}) overlaps "
                         f"'{b['name']}' ({b['start_raw']}-{b['end_raw']})")

    # unverifiable_company_shell -- LOW confidence, suffix heuristic
    for c in companies:
        name = (c.get("name") or "").lower()
        if any(name.endswith(suf) or f" {suf}" in name for suf in SHELL_SUFFIXES) and len(name.split()) <= 4:
            flag("unverifiable_company_shell", f"generic-sounding employer name: '{c.get('name')}'")
            break

    return matched, evidence


def score_candidate(candidate_id: str, extracted: dict, raw_text: str, all_candidates: list) -> dict:
    matched, evidence = score_fields(extracted, raw_text)

    sim = similarity_check.check(candidate_id, raw_text, all_candidates)
    if sim["flagged"]:
        matched.append("template_reuse_across_candidates")
        evidence["template_reuse_across_candidates"] = (
            f"near-duplicate of {sim['most_similar_candidate']} (ratio={sim['similarity_ratio']:.2f})")

    raw_score = sum(BY_ID[f]["weight"] for f in matched)
    fraud_score = round(100 * raw_score / MAX_POSSIBLE_SCORE, 1)
    reasoning = "; ".join(f"{fid} [{CONFIDENCE.get(fid,'?')}]: {ev}" for fid, ev in evidence.items())
    return {"matched_flags": matched, "fraud_score": fraud_score, "reasoning": reasoning}
