# journal_club/journals_catalog.py
"""
Static catalog of major medical journals.
Each entry: name, publisher, toc_url, issn
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    publisher: str      # Used by toc_scraper to pick the right parser
    toc_url: str
    issn: str | None = None


CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        name="New England Journal of Medicine",
        publisher="nejm",
        toc_url="https://www.nejm.org/toc/nejm/current",
        issn="0028-4793",
    ),
    CatalogEntry(
        name="JAMA",
        publisher="jama",
        toc_url="https://jamanetwork.com/journals/jama/issue/current",
        issn="0098-7484",
    ),
    CatalogEntry(
        name="The Lancet",
        publisher="lancet",
        toc_url="https://www.thelancet.com/journals/lancet/issue/current",
        issn="0140-6736",
    ),
    CatalogEntry(
        name="Nature Medicine",
        publisher="nature",
        toc_url="https://www.nature.com/nm/current-issue",
        issn="1078-8956",
    ),
    CatalogEntry(
        name="BMJ",
        publisher="bmj",
        toc_url="https://www.bmj.com/content/current",
        issn="0959-8138",
    ),
    CatalogEntry(
        name="Annals of Internal Medicine",
        publisher="acpjournals",
        toc_url="https://www.acpjournals.org/toc/aim/current",
        issn="0003-4819",
    ),
    CatalogEntry(
        name="Circulation",
        publisher="ahajournals",
        toc_url="https://www.ahajournals.org/toc/circ/current",
        issn="0009-7322",
    ),
    CatalogEntry(
        name="JACC",
        publisher="jacc",
        toc_url="https://www.jacc.org/toc/jacc/current",
        issn="0735-1097",
    ),
    CatalogEntry(
        name="CHEST",
        publisher="chest",
        toc_url="https://journal.chestnet.org/current",
        issn="0012-3692",
    ),
    CatalogEntry(
        name="Journal of Clinical Oncology",
        publisher="asco",
        toc_url="https://ascopubs.org/toc/jco/current",
        issn="0732-183X",
    ),
    CatalogEntry(
        name="Gut",
        publisher="bmj",
        toc_url="https://gut.bmj.com/content/current",
        issn="0017-5749",
    ),
    CatalogEntry(
        name="Blood",
        publisher="blood",
        toc_url="https://ashpublications.org/blood/issue",
        issn="0006-4971",
    ),
    CatalogEntry(
        name="Diabetes Care",
        publisher="diabetesjournals",
        toc_url="https://diabetesjournals.org/care/issue/current",
        issn="0149-5992",
    ),
    CatalogEntry(
        name="NEJM Evidence",
        publisher="nejm",
        toc_url="https://evidence.nejm.org/toc/evid/current",
        issn="2766-5526",
    ),
    CatalogEntry(
        name="JAMA Internal Medicine",
        publisher="jama",
        toc_url="https://jamanetwork.com/journals/jamainternalmedicine/issue/current",
        issn="2168-6106",
    ),
]
