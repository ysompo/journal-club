from dataclasses import dataclass
import yaml


@dataclass
class Config:
    huji_email: str
    huji_password: str
    output_dir: str
    chrome_profile: str
    chrome_path: str = ""   # optional override; auto-detected if empty


def load_config(path: str = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config(
        huji_email=data["huji_email"],
        huji_password=data["huji_password"],
        output_dir=data["output_dir"],
        chrome_profile=data["chrome_profile"],
        chrome_path=data.get("chrome_path", ""),
    )
