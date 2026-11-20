
import os
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API = "https://api.nextdns.io"
PROFILE = os.environ["CLIENT_ID"]
SECRET = os.environ["AUTH_SECRET"]
APPLY = os.getenv("APPLY_CLEANUP") == "true"

def request(method, path):
    req = Request(
        API + path,
        headers={"X-Api-Key": SECRET},
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except HTTPError as e:
        print(f"NextDNS API error: {e.code}")
        raise

# Load the desired records
desired = {}
for line in Path("filtered-hosts").read_text().splitlines():
    parts = line.split()
    if len(parts) != 2:
        raise RuntimeError("Invalid filtered-hosts line")
    ip, domain = parts
    desired[domain] = ip

if not 1 <= len(desired) <= 500:
    raise RuntimeError("Invalid number of desired records")

if "chatgpt.com" not in desired:
    raise RuntimeError("ChatGPT record missing")

# Get current rewrites
response = request("GET", f"/profiles/{PROFILE}/rewrites")
current = response["data"]

if not isinstance(current, list):
    raise RuntimeError("Unexpected API response")

# Save a backup of the current rules
Path("rewrites-backup.json").write_text(
    json.dumps(current, indent=2, ensure_ascii=False)
)

keep = set(desired.items())
obsolete = [
    item for item in current
    if (item.get("name"), item.get("content")) not in keep
]

print(f"Existing records: {len(current)}")
print(f"Desired records: {len(desired)}")
print(f"Records to remove: {len(obsolete)}")

for item in obsolete:
    print("REMOVE:", item.get("name"), item.get("content"))

if not APPLY:
    print("DRY RUN: nothing was deleted")
    sys.exit(0)

if os.getenv("CONFIRM_PROFILE") != PROFILE:
    raise RuntimeError("Profile confirmation mismatch")

for item in obsolete:
    record_id = item.get("id")
    if not record_id:
        raise RuntimeError("Rewrite ID missing")
    request(
        "DELETE",
        f"/profiles/{PROFILE}/rewrites/{record_id}"
    )

print("Cleanup completed")
