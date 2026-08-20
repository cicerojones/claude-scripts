#!/usr/bin/env python3
"""Append a GTD capture to gtd/inbox.org as a well-formed org headline.

Append-only by design: this script never reads or rewrites existing
headlines, it only adds one new top-level headline at the end of the
file. See gtd/CONVENTIONS.org for the schema.

Usage:
    ./capture.py "call dentist about appointment"
    ./capture.py --tag calls "call dentist about appointment"
    echo "water the plants" | ./capture.py
"""
import argparse
import datetime
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
INBOX = REPO_ROOT / "gtd" / "inbox.org"

VALID_TAGS = {"calls", "computer", "errand", "home", "waiting", "agenda"}


def format_headline(text: str, tag: str | None) -> str:
    now = datetime.datetime.now().strftime("[%Y-%m-%d %a %H:%M]")
    tag_str = f" :@{tag}:" if tag else ""
    return (
        f"* TODO {text}{tag_str}\n"
        f":PROPERTIES:\n"
        f":CREATED:  {now}\n"
        f":CAPTURED-BY: claude\n"
        f":END:\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="*", help="capture text (reads stdin if omitted)")
    parser.add_argument("--tag", choices=sorted(VALID_TAGS), default=None,
                         help="context tag")
    parser.add_argument("--no-commit", action="store_true",
                         help="skip the git commit")
    args = parser.parse_args()

    text = " ".join(args.text).strip() if args.text else sys.stdin.read().strip()
    if not text:
        parser.error("no capture text given (pass as an argument or pipe via stdin)")

    headline = format_headline(text, args.tag)
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with INBOX.open("a") as f:
        f.write(headline)

    print(f"Captured to {INBOX.relative_to(REPO_ROOT)}:")
    print(headline)

    if not args.no_commit:
        subprocess.run(["git", "add", str(INBOX)], check=True, cwd=REPO_ROOT)
        subprocess.run(
            ["git", "commit", "-m", f"capture: {text[:60]}"],
            check=True,
            cwd=REPO_ROOT,
        )


if __name__ == "__main__":
    main()
