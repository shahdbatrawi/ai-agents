"""Explicit diagnostic: uses the local key, sends no resume, prints no secrets."""
from pathlib import Path
import sys
import requests
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[2]
key = dotenv_values(root / '.env').get('OPENROUTER_API_KEY', '')
if not key:
    print('Missing OPENROUTER_API_KEY in the repository root .env')
    sys.exit(1)
try:
    response = requests.get(
        'https://openrouter.ai/api/v1/auth/key',
        headers={'Authorization': 'Bearer ' + key}, timeout=20,
    )
    print('Authentication HTTP:', response.status_code)
    if response.status_code != 200:
        message = str(response.json().get('error', {}).get('message', 'Authentication failed'))
        print(message.replace(key, '[REDACTED]'))
        sys.exit(1)
    print('Authenticated. This verifies the key only, not model availability.')
except (requests.RequestException, ValueError):
    print('Connection or response error. No key data is printed.')
    sys.exit(1)
