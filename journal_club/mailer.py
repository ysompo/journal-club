# journal_club/mailer.py
"""
Send the reading list as an email with PDF attachments.
Uses stdlib smtplib (no external dependency).
"""
from __future__ import annotations

import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path


def send_reading_list(
    articles: list[dict],
    to_addr: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
) -> int:
    """
    Build and send the reading-list email.
    articles: list of dicts from storage.get_reading_list()
    Returns number of PDF attachments included.
    """
    msg = MIMEMultipart()
    msg["Subject"] = f"Journal Club Reading List ({len(articles)} articles)"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    # Build plain-text body
    lines = ["Your Journal Club reading list:\n"]
    for i, a in enumerate(articles, 1):
        authors = a.get("authors", [])
        authors_str = ", ".join(authors[:3])
        if len(authors) > 3:
            authors_str += " et al."
        pdf_note = "(PDF attached)" if a.get("pdf_path") else "(PDF not yet downloaded)"
        lines.append(f"{i}. {a['title']}")
        lines.append(f"   {a.get('journal_name', '')} · {a.get('issue_label', '')}")
        if authors_str:
            lines.append(f"   {authors_str}")
        lines.append(f"   {a.get('url', '')} {pdf_note}")
        lines.append("")

    msg.attach(MIMEText("\n".join(lines), "plain", "utf-8"))

    # Attach PDFs
    attached = 0
    for a in articles:
        pdf_path = a.get("pdf_path")
        if not pdf_path:
            continue
        p = Path(pdf_path)
        if not p.exists():
            continue
        part = MIMEBase("application", "pdf")
        part.set_payload(p.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=p.name)
        msg.attach(part)
        attached += 1

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_addr, msg.as_string())

    return attached
