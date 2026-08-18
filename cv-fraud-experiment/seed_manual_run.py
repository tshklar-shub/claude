"""
One-off script loading a manually-generated batch (generated and scored by
Claude directly in-conversation, standing in for the API calls extract_cv.py /
score_cv.py would normally make) into the SQLite DB, so evaluate.py can run
against real stored results.

Each CV was written by Claude first; the extraction and red-flag judgment
below were then done as a separate, independent read of the CV text (not by
copying back the flags that were deliberately injected), matching what a real
extract_cv.py + score_cv.py API call pass would do.
"""

from pathlib import Path

import db
from redflags import flags_by_id, MAX_POSSIBLE_SCORE

CV_DIR = Path(__file__).parent / "data" / "cvs"

BY_ID = flags_by_id()


def score(matched_flags):
    raw = sum(BY_ID[f]["weight"] for f in matched_flags)
    return round(100 * raw / MAX_POSSIBLE_SCORE, 1)


CANDIDATES = [
    # --- clean ---
    dict(id="c1a2b3c4", file="clean_c1a2b3c4.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "Maria Chen", "email_domain_type": "personal_free", "years_experience": 8,
                     "jobs_last_5_years": 2, "linkedin_url": "present", "github_url": "present"},
         matched=["free_email_domain"],
         reasoning="protonmail.com is a personal free-email provider; otherwise consistent, verifiable history."),
    dict(id="d5e6f7a8", file="clean_d5e6f7a8.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "David Okafor", "email_domain_type": "company", "years_experience": 6,
                     "jobs_last_5_years": 1, "linkedin_url": "present", "github_url": "present"},
         matched=[], reasoning="No red-flag evidence found; consistent progression and named reference."),
    dict(id="b9c0d1e2", file="clean_b9c0d1e2.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "Priya Raman", "email_domain_type": "personal_free", "years_experience": 5,
                     "jobs_last_5_years": 2, "linkedin_url": "present", "github_url": "present"},
         matched=["free_email_domain"], reasoning="gmail.com address; otherwise consistent and verifiable."),
    dict(id="a3b4c5d6", file="clean_a3b4c5d6.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "James Whitfield", "email_domain_type": "personal_free", "years_experience": 10,
                     "jobs_last_5_years": 1, "linkedin_url": "present", "github_url": "present"},
         matched=["free_email_domain"], reasoning="outlook.com address; long stable tenures otherwise."),
    dict(id="e7f8a9b0", file="clean_e7f8a9b0.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "Laura Bianchi", "email_domain_type": "company", "years_experience": 7,
                     "jobs_last_5_years": 1, "linkedin_url": "present", "github_url": "present"},
         matched=[], reasoning="No red-flag evidence found; company email matches current employer."),
    dict(id="c1d2e3f4", file="clean_c1d2e3f4.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "Tom Reyes", "email_domain_type": "company", "years_experience": 9,
                     "jobs_last_5_years": 1, "linkedin_url": "present", "github_url": "present"},
         matched=[], reasoning="No red-flag evidence found; company email matches current employer."),
    dict(id="f5a6b7c8", file="clean_f5a6b7c8.txt", true_label="clean", true_flags=[],
         extracted={"full_name": "Anika Patel", "email_domain_type": "company", "years_experience": 6,
                     "jobs_last_5_years": 1, "linkedin_url": "present", "github_url": "present"},
         matched=[], reasoning="No red-flag evidence found; company email matches current employer."),

    # --- fraud ---
    dict(id="11223344", file="fraud_11223344.txt", true_label="fraud",
         true_flags=["name_spelling_inconsistent", "thin_linkedin", "free_email_domain"],
         extracted={"full_name": "Kevin Park", "email_domain_type": "personal_free", "years_experience": 3,
                     "jobs_last_5_years": 2, "linkedin_url": "present (k-parke-tech)", "github_url": None,
                     "name_spelling_variants_found": ["Kevin Park", "k-parke-tech"]},
         matched=["free_email_domain", "name_spelling_inconsistent", "overly_polished_language"],
         reasoning="gmail address; LinkedIn slug 'k-parke' spells the surname differently than the header "
                    "'Park'; summary reads as generic templated boilerplate."),
    dict(id="55667788", file="fraud_55667788.txt", true_label="fraud",
         true_flags=["sparse_recent_history", "employment_gaps_unexplained", "reference_personal_contact_only"],
         extracted={"full_name": "Steven Cole", "email_domain_type": "personal_free", "years_experience": 3,
                     "jobs_last_5_years": 2, "employment_gaps": [{"between": ["2023", "2024"], "months": 12}],
                     "references": [{"contact_type": "personal_cell"}, {"contact_type": "personal_email"}]},
         matched=["free_email_domain", "sparse_recent_history", "employment_gaps_unexplained",
                  "reference_personal_contact_only"],
         reasoning="yahoo address; verifiable history only starts Feb 2025; explicit ~12-month gap with vague "
                    "justification; references explicitly personal cell/email only, no company line offered."),
    dict(id="99aabbcc", file="fraud_99aabbcc.txt", true_label="fraud",
         true_flags=["illogical_progression", "high_job_turnover", "thin_github", "overly_polished_language"],
         extracted={"full_name": "Michael Torres", "email_domain_type": "personal_free", "years_experience": 2,
                     "jobs_last_5_years": 4, "github_url": None},
         matched=["free_email_domain", "illogical_progression", "high_job_turnover", "thin_github",
                  "overly_polished_language"],
         reasoning="gmail address; reaches 'Staff Engineer' title within under 2 years of total career, which "
                    "is inconsistent with typical leveling; 4 employers in under 2 years; no GitHub/portfolio "
                    "link provided; summary is generic buzzword-heavy boilerplate."),
    dict(id="ddeeffgg", file="fraud_ddeeffgg.txt", true_label="fraud",
         true_flags=["phone_format_suspicious", "address_implausible", "thin_linkedin"],
         extracted={"full_name": "Robert Kim", "email_domain_type": "personal_free", "phone": "+82 10 5555 0123",
                     "location_claimed": "United States", "years_experience": 7,
                     "linkedin_url": "present (robertkim2024)"},
         matched=["free_email_domain", "phone_format_suspicious", "address_implausible", "thin_linkedin"],
         reasoning="gmail address; phone carries a South Korean (+82) country code while location is claimed "
                    "as 'United States' with no city/state given; LinkedIn handle is a generic auto-style slug "
                    "with no corroborating detail."),
    dict(id="hhiijjkk", file="fraud_hhiijjkk.txt", true_label="fraud",
         true_flags=["sparse_recent_history", "name_spelling_inconsistent", "reference_personal_contact_only",
                     "free_email_domain"],
         extracted={"full_name": "Daniel Osei", "email_domain_type": "personal_free", "years_experience": 1,
                     "jobs_last_5_years": 1, "name_spelling_variants_found": ["Daniel Osei", "Dan Osei"],
                     "references": [{"contact_type": "personal_cell"}, {"contact_type": "personal_email"}]},
         matched=["free_email_domain", "sparse_recent_history", "name_spelling_inconsistent",
                  "reference_personal_contact_only"],
         reasoning="gmail address; only one role on record, starting Aug 2024, no prior history at all; "
                    "summary uses 'Dan Osei' vs header 'Daniel Osei'; references explicitly personal-only."),
]


def main():
    conn = db.connect()
    for c in CANDIDATES:
        raw_text = (CV_DIR / c["file"]).read_text()
        db.insert_candidate(conn, c["id"], c["file"], raw_text, true_label=c["true_label"],
                             true_injected_flags=c["true_flags"])
        db.insert_extraction(conn, c["id"], c["extracted"])
        s = score(c["matched"])
        db.insert_score(conn, c["id"], s, c["matched"], c["reasoning"])
        print(f"{c['id']:10s} {c['true_label']:6s} score={s:5.1f}  matched={c['matched']}")
    conn.close()
    print(f"\nLoaded {len(CANDIDATES)} candidates into the DB.")


if __name__ == "__main__":
    main()
