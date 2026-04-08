import pytest
from journal_club.router import detect_publisher, Publisher

@pytest.mark.parametrize("url,expected", [
    ("https://jamanetwork.com/journals/jama/article-abstract/2844116", Publisher.JAMA),
    ("https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/123", Publisher.JAMA),
    ("https://journals.lww.com/greenjournal/citation/2026/04001/foo.aspx", Publisher.OVID),
    ("https://ovidsp.ovid.com/ovidweb.cgi?T=JS&PAGE=reference&D=med24", Publisher.OVID),
    ("https://www.sciencedirect.com/science/article/pii/S0140673624001234", Publisher.ELSEVIER),
    ("https://www.ajog.org/article/S0002-9378(24)00123-4/fulltext", Publisher.ELSEVIER),
    ("https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(24)00001-X/fulltext", Publisher.ELSEVIER),
    ("https://www.nature.com/articles/s41591-026-04256-2", Publisher.SPRINGER_NATURE),
    ("https://link.springer.com/article/10.1007/s00404-024-01234-5", Publisher.SPRINGER_NATURE),
    ("https://www.nejm.org/doi/full/10.1056/NEJMoa2400001", Publisher.OPENATHENS_GENERIC),
    ("https://www.bmj.com/content/385/bmj.q1234", Publisher.OPENATHENS_GENERIC),
    ("https://academic.oup.com/jcem/article/109/1/1/1234567", Publisher.OPENATHENS_GENERIC),
    ("https://onlinelibrary.wiley.com/doi/10.1111/jog.12345", Publisher.OPENATHENS_GENERIC),
    ("https://www.thieme-connect.com/products/ejournals/abstract/1234", Publisher.OPENATHENS_GENERIC),
    ("https://www.annualreviews.org/doi/abs/10.1146/annurev-001", Publisher.OPENATHENS_GENERIC),
])
def test_detect_publisher(url, expected):
    assert detect_publisher(url) == expected
