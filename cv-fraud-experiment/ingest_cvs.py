"""
Normalize a folder of real CVs (.pdf, .docx, .txt) into plain-text files the
rest of the pipeline can consume.

Usage:
    python3 ingest_cvs.py --src /path/to/real/cvs --out data/real_cvs_txt
"""

import argparse
from pathlib import Path


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs)


def read_txt(path: Path) -> str:
    return path.read_text(errors="replace")


READERS = {".pdf": read_pdf, ".docx": read_docx, ".txt": read_txt}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=str, required=True, help="folder containing real CVs")
    ap.add_argument("--out", type=str, default="data/real_cvs_txt")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(__file__).parent / args.out
    out.mkdir(parents=True, exist_ok=True)

    ok, skipped = 0, []
    for path in sorted(src.iterdir()):
        if not path.is_file():
            continue
        reader = READERS.get(path.suffix.lower())
        if reader is None:
            skipped.append((path.name, "unsupported file type"))
            continue
        try:
            text = reader(path)
        except Exception as e:
            skipped.append((path.name, f"failed to parse: {e}"))
            continue
        if not text.strip():
            skipped.append((path.name, "extracted empty text (likely a scanned/image PDF -- needs OCR first)"))
            continue

        out_name = path.stem.replace(" ", "_") + ".txt"
        (out / out_name).write_text(text)
        ok += 1
        print(f"  ok    {path.name} -> {out_name}")

    for name, reason in skipped:
        print(f"  SKIP  {name}: {reason}")

    print(f"\nIngested {ok} CVs into {out}. {len(skipped)} skipped.")


if __name__ == "__main__":
    main()
