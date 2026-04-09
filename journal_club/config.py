from dataclasses import dataclass, field
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


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=data["huji_email"],
        huji_password=data["huji_password"],
        output_dir=data["output_dir"],
        chrome_profile=data["chrome_profile"],
        chrome_path=data.get("chrome_path", ""),
        resend_api_key=data.get("resend_api_key", ""),
        resend_from=data.get("resend_from", ""),
        email_to_1=data.get("email_to_1", ""),
        email_to_2=data.get("email_to_2", ""),
        email_to_3=data.get("email_to_3", ""),
    )
