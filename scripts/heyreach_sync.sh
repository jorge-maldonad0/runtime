#!/bin/bash
source /root/.hermes/.env 2>/dev/null
exec python3 /root/.hermes/skills/gitm/gitm-heyreach-sync/fetch_heyreach.py
