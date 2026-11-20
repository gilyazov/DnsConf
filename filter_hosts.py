
from urllib.request import urlopen
from ipaddress import ip_address

SOURCE = (
    "https://raw.githubusercontent.com/"
    "Internet-Helper/GeoHideDNS/"
    "main/hosts/eu/hosts"
)

DOMAINS = (
    "chatgpt.com",
    "openai.com",
    "oaistatic.com",
    "oaiusercontent.com",
)

# Проверенные с MacBook европейские серверы
PREFERRED_IPS = (
    "5.175.161.3",
    "5.175.161.40",
)

REQUIRED_HOSTS = (
    "chatgpt.com",
    "auth.openai.com",
)


def allowed(host):
    return any(
        host == domain or host.endswith("." + domain)
        for domain in DOMAINS
    )


candidates = {}

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

    if ip not in PREFERRED_IPS:
        continue

    for host in hosts:
        host = host.lower().replace("\\.", ".").rstrip(".")

        if allowed(host):
            candidates.setdefault(host, set()).add(ip)


result = {}

for host, available_ips in candidates.items():
    for ip in PREFERRED_IPS:
        if ip in available_ips:
            result[host] = ip
            break


missing = [
    host for host in REQUIRED_HOSTS
    if host not in result
]

if missing:
    raise RuntimeError(
        "Missing required EU rewrites: " + ", ".join(missing)
    )

if len(result) > 500:
    raise RuntimeError("NextDNS rewrite limit exceeded")

with open("filtered-hosts", "w", encoding="utf-8") as output:
    for host, ip in sorted(result.items()):
        output.write(f"{ip} {host}\n")

print(f"Generated {len(result)} EU rewrites")
print(f"Source: {SOURCE}")

for host in REQUIRED_HOSTS:
    print(f"{host} -> {result[host]}")
