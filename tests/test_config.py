import pytest
import os
import textwrap
import tempfile
from journal_club.config import load_config


def test_load_config_reads_fields(tmp_path):
    yaml_text = textwrap.dedent("""\
        huji_email: user@mail.huji.ac.il
        huji_password: secret123
        output_dir: /tmp/pdfs
        chrome_profile: /tmp/chrome-jc
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    cfg = load_config(str(cfg_file))
    assert cfg.huji_email == "user@mail.huji.ac.il"
    assert cfg.huji_password == "secret123"
    assert cfg.output_dir == "/tmp/pdfs"


def test_load_config_missing_key_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("huji_email: x\n")
    with pytest.raises(KeyError):
        load_config(str(cfg_file))
