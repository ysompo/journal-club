# journal_club/mailer.py
"""
Send the reading list via Resend (https://resend.com).
The app owner holds the API key and from-address; recipients are configured
per-installation in Settings. No SMTP setup required for end users.
"""
from __future__ import annotations

import base64
from pathlib import Path

import resend


def send_reading_list(
    articles: list[dict],
    api_key: str,
    from_addr: str,
    to_addrs: list[str],
) -> int:
    """
    Send the reading list email via Resend.
    articles : list of dicts from storage.get_reading_list()
    api_key  : Resend API key
    from_addr: verified sender address, e.g. "Journal Club <noreply@yourdomain.com>"
    to_addrs : list of recipient email addresses (up to 3)
    Returns number of PDF attachments included.
    """
    resend.api_key = api_key

    # Auto-fix bare domain (e.g. "labor-ai.org" → "Journal Club <noreply@labor-ai.org>")
    if from_addr and "@" not in from_addr and "." in from_addr:
        from_addr = f"Journal Club <noreply@{from_addr}>"

    # ── Build HTML body ───────────────────────────────────────────────────────
    rows = []
    for i, a in enumerate(articles, 1):
        authors = a.get("authors", [])
        authors_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        pdf_badge = (
            '<span style="color:#166534;background:#dcfce7;padding:1px 6px;border-radius:4px;font-size:11px;">PDF attached</span>'
            if a.get("pdf_path")
            else '<span style="color:#92400e;background:#fef3c7;padding:1px 6px;border-radius:4px;font-size:11px;">No PDF</span>'
        )
        rows.append(f"""
        <tr style="border-bottom:1px solid #f1f5f9;">
          <td style="padding:12px 8px;vertical-align:top;color:#64748b;font-size:13px;">{i}</td>
          <td style="padding:12px 8px;vertical-align:top;">
            <div style="font-weight:600;color:#1e293b;margin-bottom:3px;">{a.get('title','')}</div>
            <div style="color:#64748b;font-size:12px;margin-bottom:4px;">{a.get('journal_name','')} · {a.get('issue_label','')}</div>
            {"<div style='color:#94a3b8;font-size:12px;margin-bottom:4px;'>" + authors_str + "</div>" if authors_str else ""}
            <div>{pdf_badge} &nbsp;<a href="{a.get('url','')}" style="font-size:12px;color:#005977;">Open article →</a></div>
          </td>
        </tr>""")

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:640px;margin:0 auto;color:#1e293b;">
      <div style="background:#005977;padding:24px 32px;border-radius:8px 8px 0 0;">
        <h1 style="color:white;margin:0;font-size:20px;font-weight:700;">Journal Club</h1>
        <p style="color:rgba(255,255,255,0.75);margin:4px 0 0;font-size:13px;">Reading List · {len(articles)} article{'s' if len(articles)!=1 else ''}</p>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:24px 32px;">
        <table style="width:100%;border-collapse:collapse;">
          {''.join(rows)}
        </table>
        <p style="margin-top:20px;font-size:11px;color:#94a3b8;">
          Sent from Journal Club · HUJI PDF Library
        </p>
      </div>
    </div>"""

    # ── Build attachments ─────────────────────────────────────────────────────
    attachments = []
    attached = 0
    for a in articles:
        pdf_path = a.get("pdf_path")
        if not pdf_path:
            continue
        p = Path(pdf_path)
        if not p.exists():
            continue
        content = base64.b64encode(p.read_bytes()).decode()
        attachments.append({"filename": p.name, "content": content})
        attached += 1

    # ── Send via Resend ───────────────────────────────────────────────────────
    params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": to_addrs,
        "subject": f"Journal Club Reading List ({len(articles)} articles)",
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments

    resend.Emails.send(params)
    return attached
