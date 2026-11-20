
import os
import json
import time
import ipaddress
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import HTTPError, URLError

BASE = "https://api.nextdns.io"
PROFILE = os.environ["CLIENT_ID"].strip()
SECRET = os.environ["AUTH_SECRET"].strip()
CONFIRM = os.getenv("CONFIRM_PROFILE", "").strip()
APPLY = os.getenv("APPLY_CLEANUP") == "true"


def api(method, path, payload=None):
    body = None
    headers = {"X-Api-Key": SECRET}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    max_attempts = 12

    for attempt in range(max_attempts):
        req = Request(
            BASE + path,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(req, timeout=40) as r:
                raw = r.read()
                result = json.loads(raw) if raw else {}

            if isinstance(result, dict) and result.get("errors"):
                raise RuntimeError(
                    f"NextDNS API errors: {result['errors']}"
                )

            return result

        except HTTPError as e:
            detail = e.read().decode(errors="replace")

            if e.code == 429:
                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        "NextDNS rate limit persisted "
                        "after all retries"
                    ) from e

                retry_after = e.headers.get("Retry-After")
                try:
                    wait = float(retry_after)
                    if not 1 <= wait <= 600:
                        wait = 60
                except (TypeError, ValueError):
                    wait = min(60 * (attempt + 1), 180)

                print(
                    f"Rate limit reached. "
                    f"Waiting {wait:.0f} seconds "
                    f"(retry {attempt + 1}/{max_attempts - 1})",
                    flush=True,
                )

                time.sleep(wait)
                continue

            raise RuntimeError(
                f"{method} failed: HTTP {e.code}: {detail}"
            ) from e

        except URLError as e:
            raise RuntimeError(
                f"Network error: {e.reason}"
            ) from e

    raise RuntimeError("NextDNS API retries exhausted")


def get_all_rewrites():
    response = api(
        "GET",
        f"/profiles/{PROFILE}/rewrites"
    )

    items = response.get("data")

    if not isinstance(items, list):
        raise RuntimeError(
            "Invalid NextDNS rewrites response"
        )

    if len(items) > 500:
        raise RuntimeError(
            "Unexpected rewrite count over 500"
        )

    return items

def load_desired():
    desired = {}
    for raw in Path("filtered-hosts").read_text().splitlines():
        parts = raw.split()
        if not parts:
            continue
        if len(parts) != 2:
            raise RuntimeError(f"Invalid hosts line: {raw}")
        ip, name = parts
        ipaddress.ip_address(ip)
        name = name.lower().rstrip(".")
        if name.startswith("*.") or "\\" in name:
            raise RuntimeError(f"Invalid domain: {name}")
        if name in desired and desired[name] != ip:
            raise RuntimeError(f"Duplicate domain: {name}")
        desired[name] = ip
    if not 1 <= len(desired) <= 500:
        raise RuntimeError("Desired count outside 1..500")
    if "chatgpt.com" not in desired:
        raise RuntimeError("Missing chatgpt.com")
    return desired

def main():
    if not PROFILE or not SECRET:
        raise RuntimeError("Missing NextDNS credentials")

    # Confirm the actual target profile
    profile = api("GET", f"/profiles/{PROFILE}")
    info = profile.get("data", {})
    if info.get("id") != PROFILE:
        raise RuntimeError("Profile ID verification failed")
    print("Verified NextDNS profile:", info.get("name"))
    print("Profile ID:", PROFILE)

    desired = load_desired()
    current = get_all_rewrites()

    # Backup before any modification
    backup = {
        "profile_id": PROFILE,
        "profile_name": info.get("name"),
        "rewrites": current
    }
    Path("rewrites-backup.json").write_text(
        json.dumps(backup, indent=2, ensure_ascii=False)
    )
    print("Backup saved")

    # Keep only exact matches
    matching = set()
    obsolete = []
    for item in current:
        name = item.get("name")
        content = item.get("content")
        record_id = item.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise RuntimeError("Rewrite ID missing")
        if (name in desired and
            desired[name] == content and
            name not in matching):
            matching.add(name)
        else:
            obsolete.append(item)

    additions = {
        name: ip for name, ip in desired.items()
        if name not in matching
    }

    print("Existing:", len(current))
    print("Desired:", len(desired))
    print("To delete:", len(obsolete))
    print("To add:", len(additions))

    if not APPLY:
        print("DRY RUN - no changes made")
        return

    if CONFIRM != PROFILE:
        raise RuntimeError("Profile confirmation mismatch")

    # Delete obsolete records
    for index, item in enumerate(obsolete, 1):
        rid = quote(item["id"], safe="")
        api("DELETE", f"/profiles/{PROFILE}/rewrites/{rid}")
        if index % 25 == 0:
            print(f"Deleted {index}/{len(obsolete)}")
        time.sleep(1)

    # Add desired records
    for index, (name, ip) in enumerate(additions.items(), 1):
        api("POST", f"/profiles/{PROFILE}/rewrites",
            {"name": name, "content": ip})
        if index % 10 == 0:
            print(f"Added {index}/{len(additions)}")
        time.sleep(1)

    # Verify final state
    final = get_all_rewrites()
    actual = {(x["name"], x["content"]) for x in final}
    expected = set(desired.items())

    if actual != expected or len(final) != len(desired):
        raise RuntimeError(
            "Final verification failed; inspect backup"
        )

    print("SUCCESS: NextDNS rewrites synchronized")
    print("Final record count:", len(final))

if __name__ == "__main__":
    main()
