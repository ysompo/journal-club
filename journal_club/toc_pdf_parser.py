# journal_club/toc_pdf_parser.py
"""
Parser for AJOG Table of Contents PDF.
Extracts article metadata including title, authors, article type, and page numbers.
"""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TOCArticle:
    """Article extracted from TOC PDF."""
    title: str
    authors: list[str]
    article_type: str
    page_number: str

    def __repr__(self):
        return f"{self.article_type}: {self.title[:60]} (p.{self.page_number})"


def parse_toc_pdf(pdf_path: str) -> list[TOCArticle]:
    """
    Parse AJOG TOC PDF and extract article information.

    PDF structure:
    - Section headers (EXPERT REVIEWS, SYSTEMATIC REVIEWS, etc.)
    - Page number (e.g., 865)
    - Article title (may span multiple lines)
    - Author list (may span multiple lines)

    Returns list of TOCArticle objects.
    """
    from PyPDF2 import PdfReader

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Could not read PDF: {e}")

    # Extract text from all pages
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text()

    articles = []
    current_article_type = "Original Research"  # Default
    lines = full_text.split('\n')
    i = 0

    # Define section headers
    section_headers = {
        "EXPERT REVIEW": "Expert Review",
        "SYSTEMATIC REVIEW": "Systematic Review",
        "CLINICAL OPINION": "Clinical Opinion",
        "SURGEON'S CORNER": "Surgeon's Corner",
        "ORIGINAL RESEARCH": "Original Research",
    }

    while i < len(lines):
        line = lines[i].strip()

        # Detect section headers (match at word boundary)
        for header_key, header_value in section_headers.items():
            if header_key in line:
                current_article_type = header_value
                i += 1
                break
        else:
            # No section header matched, check for page number (article start)
            if line and re.match(r'^\d{3,4}$', line):  # Page numbers are 3-4 digits
                page_number = line
                i += 1

                # Collect title lines (stop at next page number or section header)
                title_lines = []
                while i < len(lines):
                    title_line = lines[i].strip()
                    if not title_line:  # Skip blank lines
                        i += 1
                        continue
                    # Stop conditions
                    if re.match(r'^\d{3,4}$', title_line):  # Next page number
                        break
                    if any(h in title_line for h in section_headers.keys()):  # Section header
                        break
                    # Heuristic: stop if line looks like author list (all caps or multiple capitals)
                    if (len(title_lines) > 0 and
                        (title_line.isupper() or
                         sum(1 for w in title_line.split() if w[0].isupper()) > 5)):
                        break

                    title_lines.append(title_line)
                    i += 1

                if not title_lines:
                    continue

                # Join and clean title
                title = " ".join(title_lines)
                title = re.sub(r'\s+', ' ', title).strip()

                # Collect author lines
                author_lines = []
                while i < len(lines):
                    author_line = lines[i].strip()
                    if not author_line:
                        i += 1
                        break
                    if re.match(r'^\d{3,4}$', author_line):
                        break
                    if any(h in author_line for h in section_headers.keys()):
                        break
                    author_lines.append(author_line)
                    i += 1

                # Parse authors
                authors_text = " ".join(author_lines)
                # Split by semicolon or comma, keep only author names (skip publisher info)
                if authors_text and not "Elsevier" in authors_text:
                    authors = [a.strip() for a in re.split(r'[;,]', authors_text)
                              if a.strip() and len(a.strip()) > 2]
                else:
                    authors = []

                article = TOCArticle(
                    title=title,
                    authors=authors[:5],  # Limit to first 5 authors
                    article_type=current_article_type,
                    page_number=page_number
                )
                articles.append(article)
                continue
            else:
                i += 1

    return articles


if __name__ == "__main__":
    pdf_path = Path(__file__).parent.parent / "toc_april_2026.pdf"
    if pdf_path.exists():
        articles = parse_toc_pdf(str(pdf_path))
        print(f"Parsed {len(articles)} articles from TOC\n")
        for i, article in enumerate(articles[:10], 1):
            print(f"{i}. {article}")
            print(f"   Authors: {', '.join(article.authors[:2])}")
            print()
    else:
        print(f"PDF not found: {pdf_path}")
