"""
Regex-based field extractor, tuned to the exact template format produced by
local_generator.py. This does NOT generalize to arbitrary real-world resume
formats -- that's what extract_cv.py (Claude-based) is for. This exists so
the scoring/heuristic logic can be tuned and evaluated at scale (hundreds of
candidates) without an API key.
"""

import re

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "hotmail.com"}

ROLE_RE = re.compile(r"^(?P<title>[^,]+), (?P<company>.+?) \(Remote\) — (?P<start>[\w-]+) to (?P<end>present|[\d-]+)$")
EDU_RE = re.compile(r"^(?P<degree>.+?), (?P<institution>.+?), (?P<year>\d{4})$")


def extract_fields(raw_text: str) -> dict:
    lines = raw_text.split("\n")
    full_name = lines[0].strip()

    email, phone, location = None, None, None
    if len(lines) > 1:
        parts = [p.strip() for p in lines[1].split("|")]
        if len(parts) >= 3:
            email, phone, location = parts[0], parts[1], parts[2]

    email_domain = email.split("@")[-1] if email and "@" in email else None
    email_domain_type = "personal_free" if email_domain in FREE_EMAIL_DOMAINS else ("company" if email_domain else None)

    linkedin_match = re.search(r"linkedin\.com/in/(\S+)", raw_text)
    github_match = re.search(r"github\.com/(\S+)", raw_text)

    companies = []
    for line in lines:
        m = ROLE_RE.match(line.strip())
        if m:
            companies.append(m.groupdict())

    education = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if stripped == "EDUCATION":
            in_edu = True
            continue
        if in_edu:
            if stripped == "" or stripped == "REFERENCES":
                break
            m = EDU_RE.match(stripped)
            if m:
                education.append(m.groupdict())

    references_text = ""
    if "REFERENCES" in raw_text:
        references_text = raw_text.split("REFERENCES", 1)[1].strip()

    summary_text = ""
    if "SUMMARY" in raw_text:
        after = raw_text.split("SUMMARY", 1)[1]
        summary_text = after.split("\n\n")[0].strip()

    return {
        "full_name": full_name,
        "email": email,
        "email_domain_type": email_domain_type,
        "phone": phone,
        "location_claimed": location,
        "linkedin_handle": linkedin_match.group(1) if linkedin_match else None,
        "has_github": bool(github_match),
        "companies": companies,
        "education": education,
        "references_text": references_text,
        "summary_text": summary_text,
    }
