from enum import Enum, auto

class Publisher(Enum):
    JAMA              = auto()
    OVID              = auto()
    ELSEVIER          = auto()
    SPRINGER_NATURE   = auto()
    OPENATHENS_GENERIC = auto()

_RULES: list[tuple[list[str], Publisher]] = [
    (["jamanetwork.com"],                          Publisher.JAMA),
    (["journals.lww.com", "ovidsp.ovid.com",
      "ovid.com"],                                 Publisher.OVID),
    (["sciencedirect.com", "ajog.org",
      "thelancet.com", "cell.com",
      "elsevier.com"],                             Publisher.ELSEVIER),
    (["nature.com", "link.springer.com",
      "springer.com"],                             Publisher.SPRINGER_NATURE),
    (["nejm.org", "bmj.com",
      "academic.oup.com", "onlinelibrary.wiley.com",
      "thieme-connect.com", "annualreviews.org",
      "tandfonline.com", "karger.com",
      "acog.org"],                                 Publisher.OPENATHENS_GENERIC),
]

def detect_publisher(url: str) -> Publisher:
    for domains, publisher in _RULES:
        if any(d in url for d in domains):
            return publisher
    return Publisher.OPENATHENS_GENERIC   # best-effort fallback
