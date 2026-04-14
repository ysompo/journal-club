#!/bin/bash
pip install -r requirements-prod.txt
python -m playwright install chromium
