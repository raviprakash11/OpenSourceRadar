"""Run locally once to obtain a Google OAuth refresh token for GitHub Actions.

Usage:
  pip install -r ai-research-radar/requirements.txt
  python ai-research-radar/auth_google.py path/to/client_secret.json

Copy the printed JSON into the GitHub Actions secret GOOGLE_OAUTH_CLIENT_JSON.
Do not commit client_secret.json or the printed credentials.
"""
import json
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/documents"]

if len(sys.argv) != 2:
    raise SystemExit("Usage: python ai-research-radar/auth_google.py path/to/client_secret.json")

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
payload = {
    "client_id": credentials.client_id,
    "client_secret": credentials.client_secret,
    "refresh_token": credentials.refresh_token,
    "token_uri": credentials.token_uri,
}
print("\nCopy this JSON into GitHub Actions secret GOOGLE_OAUTH_CLIENT_JSON:\n")
print(json.dumps(payload))
