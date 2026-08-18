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
import similarity_check
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

    # --- fraud: broader categories (credential fraud, overemployment, shell company, farm template reuse) ---
    dict(id="ccddeeff", file="fraud_ccddeeff.txt", true_label="fraud",
         true_flags=["education_credential_implausible", "seniority_experience_mismatch", "single_unverifiable_reference"],
         extracted={"full_name": "Ayesha Bell", "email_domain_type": "personal_free", "years_experience": 10,
                     "education": [{"institution": "Weststate Online University", "degree": "B.S. Computer Science",
                                     "grad_year": "2023"}]},
         matched=["free_email_domain", "education_credential_implausible", "seniority_experience_mismatch",
                  "single_unverifiable_reference"],
         reasoning="gmail address; institution name and same-year 'Certificate in Advanced Software Architecture' "
                    "read as diploma-mill-style credentialing; claims 'over a decade' of experience and a Staff "
                    "title while graduating in 2023, only 1 listed role; only 'available on request' offered, "
                    "no actual reference channel given at all."),
    dict(id="gghhiijj", file="fraud_gghhiijj.txt", true_label="fraud",
         true_flags=["overlapping_employment_dates", "single_unverifiable_reference"],
         extracted={"full_name": "Carlos Medina", "email_domain_type": "personal_free", "years_experience": 6,
                     "companies": [{"name": "Bluepeak Systems", "title": "Senior Software Engineer",
                                     "start": "2023-01", "end": "present"},
                                    {"name": "Fairwind Analytics", "title": "Senior Software Engineer",
                                     "start": "2023-03", "end": "present"}]},
         matched=["free_email_domain", "overlapping_employment_dates", "single_unverifiable_reference"],
         reasoning="gmail address; two roles both explicitly labeled full-time with overlapping active date "
                    "ranges (Jan 2023-present and Mar 2023-present) -- either fabricated or undisclosed "
                    "concurrent employment; only one reference offered, reachable by personal cell only."),
    dict(id="kkllmmnn", file="fraud_kkllmmnn.txt", true_label="fraud",
         true_flags=["unverifiable_company_shell"],
         extracted={"full_name": "Nina Foster", "email_domain_type": "personal_free", "years_experience": 7,
                     "companies": [{"name": "Global Tech Solutions LLC", "title": "Senior Software Engineer",
                                     "start": "2022-02", "end": "present"}]},
         matched=["free_email_domain", "unverifiable_company_shell"],
         reasoning="gmail address; current employer 'Global Tech Solutions LLC' has no location, industry, "
                    "product, or any other identifying detail across the whole document -- generic enough to "
                    "read as a possible shell entity."),
    dict(id="oopprrqq", file="fraud_oopprrqq.txt", true_label="fraud",
         true_flags=["template_reuse_across_candidates"],
         extracted={"full_name": "Marcus Webb", "email_domain_type": "personal_free", "years_experience": 3,
                     "jobs_last_5_years": 2, "linkedin_url": "present (m-webbtech)"},
         matched=["free_email_domain", "overly_polished_language"],
         reasoning="gmail address; generic buzzword summary. (Cross-candidate similarity check runs separately "
                    "below -- this CV was deliberately built as a near-clone of candidate 11223344 to test it.)"),
]


def main():
    conn = db.connect()

    # Pass 1: insert every candidate's raw text + ground truth first, so the
    # similarity check in pass 2 can compare each CV against the full set.
    for c in CANDIDATES:
        raw_text = (CV_DIR / c["file"]).read_text()
        db.insert_candidate(conn, c["id"], c["file"], raw_text, true_label=c["true_label"],
                             true_injected_flags=c["true_flags"])

    all_texts = db.fetch_all_raw_texts(conn)

    # Pass 2: real (not hand-asserted) cross-candidate similarity check, plus
    # the independently-judged per-CV flags, combined into a final score.
    for c in CANDIDATES:
        raw_text = (CV_DIR / c["file"]).read_text()
        matched = list(c["matched"])
        reasoning = c["reasoning"]

        sim = similarity_check.check(c["id"], raw_text, all_texts)
        if sim["flagged"]:
            matched.append("template_reuse_across_candidates")
            reasoning += (f" [similarity_check] near-duplicate of candidate {sim['most_similar_candidate']} "
                           f"(ratio={sim['similarity_ratio']:.2f}).")

        db.insert_extraction(conn, c["id"], c["extracted"])
        s = score(matched)
        db.insert_score(conn, c["id"], s, matched, reasoning)
        print(f"{c['id']:10s} {c['true_label']:6s} score={s:5.1f}  sim={sim['similarity_ratio']:.2f} "
              f"(vs {sim['most_similar_candidate']})  matched={matched}")

    conn.close()
    print(f"\nLoaded {len(CANDIDATES)} candidates into the DB.")


if __name__ == "__main__":
    main()
