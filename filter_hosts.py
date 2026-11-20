
from urllib.request import urlopen
from ipaddress import ip_address

SOURCE = (
    "https://raw.githubusercontent.com/"
    "Internet-Helper/GeoHideDNS/"
    "refs/heads/main/hosts/hosts"
)

DOMAINS = (
    "chatgpt.com",
    "openai.com",
    "oaistatic.com",
    "oaiusercontent.com",
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "googlevideo.com",
    "ytimg.com",
    "youtubei.googleapis.com",
)

def allowed(host):
    return any(
        host == domain or host.endswith("." + domain)
        for domain in DOMAINS
    )

result = {}
with urlopen(SOURCE, timeout=30) as response:
    lines = response.read().decode("utf-8").splitlines()

for line in lines:
    parts = line.split("#", 1)[0].split()
    if len(parts) < 2:
        continue
    ip, *hosts = parts
    try:
        ip_address(ip)
    except ValueError:
        continue
    for host in hosts:
        host = host.lower().rstrip(".")
        if allowed(host) and host not in result:
            result[host] = ip

if not result or "chatgpt.com" not in result:
    raise RuntimeError("No ChatGPT records found")

if len(result) > 500:
    raise RuntimeError("NextDNS rewrite limit exceeded")

with open("filtered-hosts", "w") as output:
    for host, ip in sorted(result.items()):
        output.write(f"{ip} {host}\n")

print(f"Generated {len(result)} rewrites")
