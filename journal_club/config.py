from dataclasses import dataclass
import yaml


@dataclass
class Config:
    huji_email: str
    huji_password: str
    output_dir: str
    chrome_profile: str
    chrome_path: str = ""
    email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=data["huji_email"],
        huji_password=data["huji_password"],
        output_dir=data["output_dir"],
        chrome_profile=data["chrome_profile"],
        chrome_path=data.get("chrome_path", ""),
        email_to=data.get("email_to", ""),
        smtp_host=data.get("smtp_host", "smtp.gmail.com"),
        smtp_port=int(data.get("smtp_port", 587)),
        smtp_user=data.get("smtp_user", ""),
        smtp_password=data.get("smtp_password", ""),
    )
