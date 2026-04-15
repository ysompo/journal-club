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
    days_per_issue: int = 7  # Approximate days between issues (7=weekly, 14=biweekly, 30=monthly)


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
        days_per_issue=30,
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
        days_per_issue=14,
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
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Journal of Clinical Oncology",
        publisher="asco",
        toc_url="https://ascopubs.org/toc/jco/current",
        issn="0732-183X",
        days_per_issue=14,
    ),
    CatalogEntry(
        name="Gut",
        publisher="bmj",
        toc_url="https://gut.bmj.com/content/current",
        issn="0017-5749",
        days_per_issue=30,
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
        days_per_issue=30,
    ),
    CatalogEntry(
        name="NEJM Evidence",
        publisher="nejm",
        toc_url="https://evidence.nejm.org/toc/evid/current",
        issn="2766-5526",
        days_per_issue=14,
    ),
    CatalogEntry(
        name="JAMA Internal Medicine",
        publisher="jama",
        toc_url="https://jamanetwork.com/journals/jamainternalmedicine/issue/current",
        issn="2168-6106",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="American Journal of Obstetrics and Gynecology",
        publisher="toc_pdf_auto",
        toc_url="https://www.ajog.org/current",
        issn="0002-9378",
        days_per_issue=30,
    ),
    # ── OB/GYN journals ──────────────────────────────────────────────────────
    CatalogEntry(
        name="Obstetrics & Gynecology (Green Journal)",
        publisher="lww",
        toc_url="https://journals.lww.com/greenjournal/toc/current",
        issn="0029-7844",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="AJOG MFM",
        publisher="elsevier",
        toc_url="https://www.ajogmfm.org/current",
        issn="2589-9333",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Ultrasound in Obstetrics & Gynecology",
        publisher="wiley",
        toc_url="https://obgyn.onlinelibrary.wiley.com/toc/14690705/current",
        issn="0960-7692",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Human Reproduction",
        publisher="oup",
        toc_url="https://academic.oup.com/humrep/issue",
        issn="0268-1161",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Fertility and Sterility",
        publisher="elsevier",
        toc_url="https://www.fertstert.org/current",
        issn="0015-0282",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="BJOG",
        publisher="wiley",
        toc_url="https://obgyn.onlinelibrary.wiley.com/toc/14710528/current",
        issn="1470-0328",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Gynecologic Oncology",
        publisher="elsevier",
        toc_url="https://www.gynecologiconcology-online.net/current",
        issn="0090-8258",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Prenatal Diagnosis",
        publisher="wiley",
        toc_url="https://obgyn.onlinelibrary.wiley.com/toc/10970223/current",
        issn="0197-3851",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Placenta",
        publisher="elsevier",
        toc_url="https://www.placentajournal.org/current",
        issn="0143-4004",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Contraception",
        publisher="elsevier",
        toc_url="https://www.contraceptionjournal.org/current",
        issn="0010-7824",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="International Journal of Gynecology & Obstetrics",
        publisher="wiley",
        toc_url="https://obgyn.onlinelibrary.wiley.com/toc/18793479/current",
        issn="0020-7292",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Reproductive BioMedicine Online",
        publisher="elsevier",
        toc_url="https://www.rbmojournal.com/current",
        issn="1472-6483",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Journal of Maternal-Fetal & Neonatal Medicine",
        publisher="taylor_francis",
        toc_url="https://www.tandfonline.com/toc/ijmf20/current",
        issn="1476-7058",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="European Journal of Obstetrics & Gynecology",
        publisher="elsevier",
        toc_url="https://www.ejog.org/current",
        issn="0301-2115",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Seminars in Perinatology",
        publisher="elsevier",
        toc_url="https://www.seminperinat.com/current",
        issn="0146-0005",
        days_per_issue=60,
    ),
    CatalogEntry(
        name="Acta Obstetricia et Gynecologica Scandinavica",
        publisher="wiley",
        toc_url="https://obgyn.onlinelibrary.wiley.com/toc/16000412/current",
        issn="0001-6349",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Journal of Gynecologic Surgery",
        publisher="liebertpub",
        toc_url="https://www.liebertpub.com/toc/gyn/current",
        issn="1042-4067",
        days_per_issue=60,
    ),
    CatalogEntry(
        name="Obstetric Anesthesia Digest",
        publisher="lww",
        toc_url="https://journals.lww.com/obstetricanesthesia/toc/current",
        issn="0275-665X",
        days_per_issue=90,
    ),
    CatalogEntry(
        name="Menopause",
        publisher="lww",
        toc_url="https://journals.lww.com/menopausejournal/toc/current",
        issn="1072-3714",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Journal of Perinatology",
        publisher="nature",
        toc_url="https://www.nature.com/jp/current-issue",
        issn="0743-8346",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Human Reproduction Update",
        publisher="oup",
        toc_url="https://academic.oup.com/humupd/issue",
        issn="1355-4786",
        days_per_issue=60,
    ),
    CatalogEntry(
        name="American Journal of Perinatology",
        publisher="thieme",
        toc_url="https://www.thieme-connect.com/products/ejournals/issue/10.1055/s-00000085",
        issn="0735-1631",
        days_per_issue=30,
    ),
    CatalogEntry(
        name="Journal of Perinatal Medicine",
        publisher="degruyter",
        toc_url="https://www.degruyter.com/journal/key/jpme/html",
        issn="0300-5577",
        days_per_issue=60,
    ),
    CatalogEntry(
        name="Reproductive Sciences",
        publisher="springer",
        toc_url="https://link.springer.com/journal/43032/volumes-and-issues",
        issn="1933-7191",
        days_per_issue=30,
    ),
]
