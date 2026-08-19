"""
Template-based synthetic CV generator that runs entirely offline (no Claude
API). Built to scale to hundreds of labeled candidates for tuning the
rule-based detector in rule_based_score.py.

Each candidate is built from a structured record first, then rendered to CV
text -- ground truth (label, injected flags, clone-parent for template-reuse
cases) is stored alongside. Deliberately decorrelates weak signals (e.g. free
email domain) from the fraud label so the detector can't shortcut on them.
"""

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

FIRST_NAMES = ["James", "Maria", "David", "Priya", "Kevin", "Laura", "Tom", "Anika", "Steven", "Michael",
               "Robert", "Daniel", "Ayesha", "Carlos", "Nina", "Marcus", "Sarah", "Wei", "Fatima", "John",
               "Elena", "Omar", "Grace", "Ben", "Chloe", "Raj", "Sofia", "Noah", "Ivy", "Lucas"]
LAST_NAMES = ["Chen", "Okafor", "Raman", "Whitfield", "Park", "Bianchi", "Reyes", "Patel", "Cole", "Torres",
              "Kim", "Osei", "Bell", "Medina", "Foster", "Webb", "Nguyen", "Silva", "Khan", "Novak",
              "Petrov", "Adeyemi", "Larsen", "Rossi", "Ibrahim", "Suzuki", "Kowalski", "Diaz", "Fischer", "Moreau"]

FREE_EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "hotmail.com"]

REAL_COMPANIES = ["Brightline Systems", "Coral Analytics", "Meridian Health Analytics", "Fenwick Pay",
                   "Cascade Cloud", "AdVantage Media", "Highline Robotics", "Northstar Retail",
                   "Lakeview Logistics", "Bexar Fintech", "CareSync Technologies", "Boston Medical Systems"]
VAGUE_SHELL_NAMES = ["Global Tech Solutions LLC", "Apex Digital Group", "Summit Enterprise Partners",
                      "Vantage Consulting LLC", "Prime Innovations Group", "Continental Business Solutions"]

REAL_INSTITUTIONS = ["University of Washington", "UT Austin", "Boston University", "University of Michigan",
                      "Colorado School of Mines", "Columbia University", "UIC", "Georgia Tech"]
DIPLOMA_MILL_INSTITUTIONS = ["Weststate Online University", "Eastwood Online University", "Pacific Coast University",
                              "National Technical University", "Continental Distance College", "Online Technical Institute"]

US_LOCATIONS = ["San Francisco, CA", "Chicago, IL", "Austin, TX", "Seattle, WA", "Boston, MA", "Denver, CO",
                "New York, NY", "Atlanta, GA", "Portland, OR", "Miami, FL"]
US_AREA_CODES = ["415", "312", "512", "206", "617", "720", "646", "404", "503", "786"]
FOREIGN_COUNTRY_CODES = ["+82 10", "+86 138", "+7 916", "+234 803", "+254 722"]

TITLE_LADDER = ["Junior Developer", "Software Engineer", "Senior Software Engineer", "Staff Software Engineer",
                "Principal Software Engineer"]

BULLET_SUBJECTS = ["the checkout service", "the internal admin tool", "the notification pipeline",
                    "the user-facing API layer", "the batch reporting system", "the search indexing service",
                    "the fraud-review dashboard", "the billing reconciliation job", "the auth service",
                    "the event-streaming layer", "the customer data platform", "the inventory sync job"]
BULLET_TEMPLATES = [
    "Built and maintained {subj}, handling core business logic",
    "Led migration of {subj} to a modern microservices architecture",
    "Reduced infrastructure costs for {subj} by optimizing resource utilization",
    "Mentored junior engineers working on {subj} and ran the on-call rotation",
    "Designed {subj}, which now powers internal analytics dashboards",
    "Owned the CI/CD pipeline for {subj} used across multiple engineering teams",
    "Improved response times for {subj} through caching and query optimization",
    "Collaborated with product and design on the specification for {subj}",
    "Wrote and maintained integration tests covering {subj}",
    "Debugged and resolved production incidents affecting {subj}",
    "Refactored {subj} from a monolith into independently deployable components",
    "Implemented monitoring and alerting for {subj}",
    "Partnered with cross-functional teams to scope and deliver {subj}",
    "Automated the manual deployment process for {subj}, cutting release time significantly",
    "Reviewed pull requests and set coding standards for the team owning {subj}",
    "Scaled {subj} to handle a 3x increase in traffic without a rewrite",
    "Cut the p99 latency of {subj} in half through targeted profiling",
    "Migrated {subj} off a deprecated internal framework with zero downtime",
    "Built the on-call runbook and alerting thresholds for {subj}",
    "Drove the technical design review process for {subj}",
]
# Cartesian product of subjects x templates gives a much larger, less collision-prone
# pool than a flat list -- important because with a small flat pool, unrelated
# candidates started coincidentally converging on near-identical bodies at scale
# (see README: a coincidental pair scored 0.911, above the true-clone floor of 0.868,
# with the old 15-bullet pool).
BULLET_POOL = [t.format(subj=s) for t in BULLET_TEMPLATES for s in BULLET_SUBJECTS]

POLISHED_PHRASES = [
    "Highly skilled and results-driven engineer with proven ability to deliver robust, scalable solutions.",
    "Passionate about delivering high-quality solutions in fast-paced environments.",
    "Consistently exceeding expectations and driving measurable business impact.",
]

# Flags grouped into clusters that render via mutually-exclusive code paths --
# sampling two flags from the same cluster onto one candidate means only one
# of them actually shows up as textual evidence, silently corrupting ground
# truth. At most one flag per cluster is sampled per candidate.
FLAG_CLUSTERS = [
    ["sparse_recent_history", "illogical_progression", "employment_gaps_unexplained",
     "high_job_turnover", "overlapping_employment_dates", "seniority_experience_mismatch"],
    ["reference_personal_contact_only", "single_unverifiable_reference"],
    ["name_spelling_inconsistent", "thin_linkedin"],
]
_CLUSTERED = {f for cluster in FLAG_CLUSTERS for f in cluster}

INDEPENDENT_FLAGS = [
    "phone_format_suspicious", "thin_github", "address_implausible",
    "overly_polished_language", "education_credential_implausible", "unverifiable_company_shell",
]

ALL_INJECTABLE_FLAGS = list(_CLUSTERED) + INDEPENDENT_FLAGS


def sample_flags(rng, k):
    """Pick up to k flags, at most one per cluster in FLAG_CLUSTERS, rest from independent flags."""
    chosen = []
    clusters = [c[:] for c in FLAG_CLUSTERS]
    rng.shuffle(clusters)
    pool = INDEPENDENT_FLAGS[:]
    rng.shuffle(pool)
    ci = 0
    while len(chosen) < k and (ci < len(clusters) or pool):
        if ci < len(clusters):
            chosen.append(rng.choice(clusters[ci]))
            ci += 1
        elif pool:
            chosen.append(pool.pop())
    return chosen[:k]


@dataclass
class Candidate:
    id: str
    label: str
    injected_flags: list = field(default_factory=list)
    clone_of: str = None
    text: str = ""


def rand_id(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(8))


def build_companies(rng, flags, base_year):
    """Returns list of dicts: name, title, start, end (strings like '2021-03')."""
    companies = []
    if "sparse_recent_history" in flags:
        start = f"{base_year - rng.choice([0, 1])}-{rng.randint(1,9):02d}"
        name = rng.choice(VAGUE_SHELL_NAMES) if "unverifiable_company_shell" in flags else rng.choice(REAL_COMPANIES)
        companies = [{"name": name, "title": "Senior Software Engineer", "start": start, "end": "present"}]
        return companies

    n = rng.randint(2, 3)
    if "high_job_turnover" in flags:
        n = rng.randint(4, 5)
        # anchor recently so the short-tenure cluster actually falls within
        # the "last 5 years" window the turnover signal depends on
        cursor_year = base_year - rng.randint(3, 4)
    else:
        cursor_year = base_year - rng.randint(6, 12)
    cursor_month = rng.randint(1, 9)
    for i in range(n):
        dur_months = rng.randint(6, 10) if "high_job_turnover" in flags else rng.randint(18, 40)
        start = f"{cursor_year}-{cursor_month:02d}"
        cursor_month += dur_months
        while cursor_month > 12:
            cursor_month -= 12
            cursor_year += 1
        is_last = i == n - 1
        end = "present" if is_last else f"{cursor_year}-{cursor_month:02d}"

        if "employment_gaps_unexplained" in flags and i == n - 2:
            cursor_month += rng.randint(6, 10)
            while cursor_month > 12:
                cursor_month -= 12
                cursor_year += 1

        name = rng.choice(VAGUE_SHELL_NAMES) if ("unverifiable_company_shell" in flags and is_last) else rng.choice(REAL_COMPANIES)
        title = TITLE_LADDER[min(i, len(TITLE_LADDER) - 1)]
        companies.append({"name": name, "title": title, "start": start, "end": end})

    if "illogical_progression" in flags:
        # collapse to a short total span but assign the top title anyway
        companies = companies[-2:] if len(companies) > 2 else companies
        for c in companies:
            pass
        companies[-1]["title"] = "Staff Software Engineer"
        span_start_year = base_year - 1
        companies[0]["start"] = f"{span_start_year}-01"
        companies[0]["end"] = f"{span_start_year}-07"
        companies[-1]["start"] = f"{span_start_year}-08"
        companies[-1]["end"] = "present"

    if "overlapping_employment_dates" in flags and len(companies) >= 2:
        companies[-2]["end"] = "present"
        companies[-1]["end"] = "present"
        companies[-1]["start"] = companies[-2]["start"]

    if "seniority_experience_mismatch" in flags:
        companies[-1]["title"] = rng.choice(["Staff Software Engineer", "Principal Software Engineer"])

    return companies


def build_candidate(rng, idx, label, base_year=2026, clone_pool=None, clone_rate=0.0):
    cid = rand_id(rng)

    # Occasionally clone an existing fraud candidate's text (facilitator-ring template reuse):
    # same body (summary/experience/education/references -- the actual "reused template"),
    # fresh surface identity (name/email/phone/linkedin/github), matching what a real
    # facilitator ring plausibly submits -- a coherent fake identity wrapped around
    # boilerplate content, not a broken CV with mismatched name and contact info.
    if label == "fraud" and clone_pool and rng.random() < clone_rate:
        parent = rng.choice(clone_pool)
        parent_lines = parent.text.split("\n")
        body_start = parent_lines.index("") if "" in parent_lines else len(parent_lines)
        parent_header = "\n".join(parent_lines[:body_start])
        body = "\n".join(parent_lines[body_start:])
        had_linkedin = "linkedin.com/in/" in parent_header
        had_github = "github.com/" in parent_header

        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{rng.randint(1,99)}@{rng.choice(FREE_EMAIL_DOMAINS)}"
        phone = f"+1 ({rng.choice(US_AREA_CODES)}) 555-{rng.randint(1000,9999)}"
        location = rng.choice(US_LOCATIONS)
        header = [f"{first} {last}", f"{email} | {phone} | {location}"]
        if had_linkedin:
            header.append(f"linkedin.com/in/{first.lower()}-{last.lower()}")
        if had_github:
            header.append(f"github.com/{first.lower()}{last.lower()}")

        new_text = "\n".join(header) + "\n" + body
        cand = Candidate(id=cid, label="fraud", injected_flags=["template_reuse_across_candidates"],
                          clone_of=parent.id, text=new_text)
        # A near-duplicate pair is symmetric -- the parent is just as
        # legitimately part of the template-reuse cluster as the clone.
        # Without this, a correct detection on the parent side reads as a
        # false positive against ground truth, when it's actually a labeling gap.
        if "template_reuse_across_candidates" not in parent.injected_flags:
            parent.injected_flags.append("template_reuse_across_candidates")
        return cand

    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    full_name = f"{first} {last}"

    flags = []
    if label == "fraud":
        k = rng.randint(2, 4)
        flags = sample_flags(rng, k)

    # weak signal, decorrelated from label: free email domain independent of fraud/clean
    use_free_email = rng.random() < (0.65 if label == "fraud" else 0.4)
    if use_free_email:
        email = f"{first.lower()}.{last.lower()}{rng.randint(1,99)}@{rng.choice(FREE_EMAIL_DOMAINS)}"
    else:
        company_slug = rng.choice(REAL_COMPANIES).lower().replace(" ", "")[:14]
        email = f"{first.lower()}.{last.lower()}@{company_slug}.com"

    location = rng.choice(US_LOCATIONS)
    if "address_implausible" in flags:
        location = "United States"

    if "phone_format_suspicious" in flags:
        phone = f"{rng.choice(FOREIGN_COUNTRY_CODES)} {rng.randint(1000,9999)}"
    else:
        phone = f"+1 ({rng.choice(US_AREA_CODES)}) 555-{rng.randint(1000,9999)}"

    years_experience = rng.randint(4, 12)
    companies = build_companies(rng, flags, base_year)

    if "name_spelling_inconsistent" in flags:
        variant_last = last[:-1] + rng.choice("xyzq") if len(last) > 3 else last + "e"
        linkedin_handle = f"{first.lower()}-{variant_last.lower()}"
    else:
        linkedin_handle = f"{first.lower()}-{last.lower()}"

    has_linkedin = "thin_linkedin" not in flags
    has_github = "thin_github" not in flags

    if "education_credential_implausible" in flags:
        institution = rng.choice(DIPLOMA_MILL_INSTITUTIONS)
        grad_year = str(base_year - rng.randint(0, 2))
    else:
        institution = rng.choice(REAL_INSTITUTIONS)
        grad_year = str(base_year - years_experience - rng.randint(0, 2))
    if "seniority_experience_mismatch" in flags:
        grad_year = str(base_year - rng.randint(0, 2))

    if "reference_personal_contact_only" in flags:
        ref_line = "References reachable via personal cell and personal email upon request."
    elif "single_unverifiable_reference" in flags:
        ref_line = "One reference available: personal cell number provided upon request."
    else:
        ref_line = f"Former manager at {companies[0]['name'] if companies else 'prior employer'}, reachable via company directory line."

    summary = f"Senior Software Engineer with {years_experience} years of backend/distributed-systems experience."
    if "overly_polished_language" in flags:
        summary = rng.choice(POLISHED_PHRASES)

    lines = [full_name]
    contact = f"{email} | {phone} | {location}"
    if has_linkedin:
        contact += f"\nlinkedin.com/in/{linkedin_handle}"
    if has_github:
        contact += f"\ngithub.com/{first.lower()}{last.lower()}"
    elif "thin_github" not in flags:
        contact += f"\ngithub.com/{first.lower()}{last.lower()}"
    lines.append(contact)
    lines.append("")
    lines.append("SUMMARY")
    lines.append(summary)
    lines.append("")
    lines.append("EXPERIENCE")
    for c in companies:
        lines.append(f"{c['title']}, {c['name']} (Remote) — {c['start']} to {c['end']}")
        for bullet in rng.sample(BULLET_POOL, rng.randint(1, 2)):
            lines.append(f"- {bullet}")
    lines.append("")
    lines.append("EDUCATION")
    lines.append(f"B.S. Computer Science, {institution}, {grad_year}")
    if "education_credential_implausible" in flags:
        lines.append(f"Certificate in Advanced Software Architecture, {institution}, {grad_year}")
    lines.append("")
    lines.append("REFERENCES")
    lines.append(ref_line)

    text = "\n".join(lines)
    return Candidate(id=cid, label=label, injected_flags=flags, text=text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--fraud-rate", type=float, default=0.35)
    ap.add_argument("--clone-rate", type=float, default=0.12, help="fraction of fraud CVs that clone an earlier fraud CV's template")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default="data/cvs_large")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(__file__).parent / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    n_fraud = round(args.n * args.fraud_rate)
    n_clean = args.n - n_fraud
    plan = ["fraud"] * n_fraud + ["clean"] * n_clean
    rng.shuffle(plan)

    candidates = []
    fraud_pool = []
    for i, label in enumerate(plan):
        cand = build_candidate(rng, i, label, clone_pool=fraud_pool, clone_rate=args.clone_rate)
        candidates.append(cand)
        if label == "fraud":
            fraud_pool.append(cand)

    manifest = []
    for c in candidates:
        fname = f"{c.label}_{c.id}.txt"
        (out_dir / fname).write_text(c.text)
        manifest.append({"id": c.id, "file": fname, "label": c.label,
                          "injected_flags": c.injected_flags, "clone_of": c.clone_of})

    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Generated {len(candidates)} candidates ({n_fraud} fraud / {n_clean} clean) -> {out_dir}")
    clone_count = sum(1 for c in candidates if c.clone_of)
    print(f"  {clone_count} fraud CVs are deliberate template clones of an earlier fraud CV")


if __name__ == "__main__":
    main()
