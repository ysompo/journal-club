from dataclasses import dataclass, field
import os
import yaml


@dataclass
class Config:
    huji_email: str
    huji_password: str
    output_dir: str
    chrome_profile: str
    chrome_path: str = ""
    resend_api_key: str = ""
    resend_from: str = ""
    email_to_1: str = ""
    email_to_2: str = ""
    email_to_3: str = ""
    admin_password: str = "changeme"
    journal_access_password: str = "changeme"


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=os.environ.get("HUJI_EMAIL") or data["huji_email"],
        huji_password=os.environ.get("HUJI_PASSWORD") or data["huji_password"],
        output_dir=os.environ.get("OUTPUT_DIR") or data["output_dir"],
        chrome_profile=os.environ.get("CHROME_PROFILE") or data["chrome_profile"],
        chrome_path=os.environ.get("CHROME_PATH") or data.get("chrome_path", ""),
        resend_api_key=os.environ.get("RESEND_API_KEY") or data.get("resend_api_key", ""),
        resend_from=os.environ.get("RESEND_FROM") or data.get("resend_from", ""),
        email_to_1=os.environ.get("EMAIL_TO_1") or data.get("email_to_1", ""),
        email_to_2=os.environ.get("EMAIL_TO_2") or data.get("email_to_2", ""),
        email_to_3=os.environ.get("EMAIL_TO_3") or data.get("email_to_3", ""),
        admin_password=os.environ.get("ADMIN_PASSWORD") or data.get("admin_password", "changeme"),
        journal_access_password=os.environ.get("JOURNAL_ACCESS_PASSWORD") or data.get("journal_access_password", "changeme"),
    )
