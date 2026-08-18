"""SQLite storage for the synthetic CV fraud-detection experiment."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "db" / "cv_fraud.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    true_label TEXT,              -- 'clean' | 'fraud' | NULL (unknown, real data)
    true_injected_flags TEXT,     -- JSON list, only set for synthetic fraud CVs
    raw_text TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extractions (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates(id),
    extracted_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scores (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates(id),
    fraud_score REAL NOT NULL,
    matched_flags TEXT NOT NULL,   -- JSON list of red flag ids
    reasoning TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def insert_candidate(conn, candidate_id, source_file, raw_text, true_label=None, true_injected_flags=None):
    conn.execute(
        "INSERT OR REPLACE INTO candidates (id, source_file, true_label, true_injected_flags, raw_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (candidate_id, source_file, true_label, json.dumps(true_injected_flags or []), raw_text),
    )
    conn.commit()


def insert_extraction(conn, candidate_id, extracted: dict):
    conn.execute(
        "INSERT OR REPLACE INTO extractions (candidate_id, extracted_json) VALUES (?, ?)",
        (candidate_id, json.dumps(extracted)),
    )
    conn.commit()


def insert_score(conn, candidate_id, fraud_score, matched_flags, reasoning):
    conn.execute(
        "INSERT OR REPLACE INTO scores (candidate_id, fraud_score, matched_flags, reasoning) VALUES (?, ?, ?, ?)",
        (candidate_id, fraud_score, json.dumps(matched_flags), reasoning),
    )
    conn.commit()


def fetch_all_raw_texts(conn):
    cur = conn.execute("SELECT id, raw_text FROM candidates")
    return cur.fetchall()


def fetch_all_results(conn):
    cur = conn.execute(
        """
        SELECT c.id, c.true_label, c.true_injected_flags, s.fraud_score, s.matched_flags
        FROM candidates c
        LEFT JOIN scores s ON s.candidate_id = c.id
        """
    )
    return cur.fetchall()
