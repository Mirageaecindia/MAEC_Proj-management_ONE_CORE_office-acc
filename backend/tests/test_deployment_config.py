"""The production stack's wiring, read from the files that deploy it.

The new stack (project maec-pm) runs on the VPS next to the old Project Management
(promanage, 127.0.0.1:8081), both Engineering Tools stacks and MAEC One Core. These checks
keep it from colliding with any of them, and keep the gate's settings required.
"""

import ipaddress
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE = ("CORE_URL", "CORE_PUBLIC_URL", "MAEC_APP_KEY", "MAEC_GATE_SECRET")
RETIRED = ("SESSION_TTL_HOURS", "LOGIN_MAX_FAILED_ATTEMPTS", "LOGIN_LOCKOUT_MINUTES", "SITE_ADDRESS")

# What the neighbours on the VPS already hold.
TAKEN_PORTS = {8080, 8081, 8082, 8001}  # old ET, old PM, new ET, Core
TAKEN_SUBNETS = ("172.30.57.0/24", "10.231.0.0/24", "10.231.1.0/24", "10.231.2.0/24")
TAKEN_IMAGES = {
    "maec-backend",
    "maec-frontend",  # old Engineering Tools
    "maec-et-backend",
    "maec-et-frontend",  # new Engineering Tools
    "maec-core",  # MAEC One Core
    "promanage-backend",
    "promanage-frontend",
    "promanage-db",  # the old Project Management (compose's default names)
}


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _compose() -> dict:
    return yaml.safe_load(_read("docker-compose.yml"))


def _default(value: str, variable: str) -> str:
    """The default a "${VARIABLE:-default}" reference falls back to."""
    match = re.search(r"\$\{" + variable + r":-([^}]+)\}", value)
    assert match, f"{variable} has no default in {value!r}"
    return match.group(1)


def _env_example(name: str = ".env.example") -> dict[str, str]:
    return dict(re.findall(r"^([A-Z_]+)=(.*)$", _read(name), re.M))


def test_the_stack_has_its_own_project_name():
    assert _compose()["name"] == "maec-pm"


def test_only_the_frontend_is_published_on_loopback_at_8083_never_8081():
    services = _compose()["services"]
    published = {name: service.get("ports", []) for name, service in services.items() if service.get("ports")}

    assert list(published) == ["frontend"]
    [mapping] = published["frontend"]
    assert mapping.startswith("127.0.0.1:") and mapping.endswith(":80")
    port = int(_default(mapping, "PM_PORT"))
    assert port == 8083
    assert port not in TAKEN_PORTS
    assert not any(":443" in str(p) or str(p).startswith(("80:", "443:")) for p in published["frontend"])


def test_the_network_is_its_own_and_overlaps_no_neighbour():
    network = _compose()["networks"]["pm_net"]
    subnet = ipaddress.ip_network(_default(network["ipam"]["config"][0]["subnet"], "PM_NET_SUBNET"))

    assert network["name"] == "maec_pm_net"
    assert subnet == ipaddress.ip_network("10.231.3.0/24")
    for taken in TAKEN_SUBNETS:
        assert not subnet.overlaps(ipaddress.ip_network(taken)), taken
    for docker_pool in ("172.16.0.0/12", "192.168.0.0/16"):  # Docker's default address pools
        assert not subnet.overlaps(ipaddress.ip_network(docker_pool))


def test_the_backend_trusts_forwarded_headers_from_the_stack_s_own_network_only():
    compose = _compose()
    subnet = compose["networks"]["pm_net"]["ipam"]["config"][0]["subnet"]
    backend = compose["services"]["backend"]

    assert backend["environment"]["TRUSTED_PROXIES"] == subnet  # the same variable: they cannot drift
    assert compose["services"]["frontend"]["environment"]["PM_NET_SUBNET"] == subnet
    assert "--no-proxy-headers" in _read("backend/Dockerfile")
    assert "--forwarded-allow-ips" not in _read("backend/Dockerfile")


def test_core_s_network_is_joined_never_created():
    compose = _compose()
    assert compose["networks"]["maec_core_net"] == {"external": True, "name": "maec_core_net"}
    assert "maec_core_net" in compose["services"]["backend"]["networks"]
    assert "maec_core_net" not in compose["services"]["frontend"]["networks"]
    assert "maec_core_net" not in compose["services"]["db"]["networks"]


def test_image_and_volume_names_clash_with_no_other_stack():
    compose = _compose()
    images = {service["image"].split(":")[0] for service in compose["services"].values() if "build" in service}

    assert images == {"maec-pm-backend", "maec-pm-frontend"}
    assert not images & TAKEN_IMAGES
    assert compose["volumes"]["db"]["name"] == "maec-pm_db"


def test_the_gate_s_settings_are_required_and_the_retired_ones_gone():
    backend = _compose()["services"]["backend"]["environment"]
    for name in GATE:
        assert re.fullmatch(r"\$\{" + name + r":\?.+\}", backend[name]), name
    for template in (".env.example", "backend/.env.example", "docker-compose.yml"):
        for retired in RETIRED:
            assert retired not in _read(template), f"{retired} in {template}"


def test_the_example_reaches_core_inside_docker_with_a_placeholder_secret():
    example = _env_example()
    assert example["CORE_URL"] == "http://maec-core:8000"
    assert example["CORE_PUBLIC_URL"] == "https://auth.mirageaec.com"
    assert example["MAEC_APP_KEY"] == "projects"
    assert example["MAEC_GATE_SECRET"] == "generate-on-the-server"  # refused at startup (test_gate.py)


def test_the_frontend_serves_plain_http_and_passes_the_forwarded_headers_on():
    caddy = _read("frontend/Caddyfile")
    assert "auto_https off" in caddy
    assert re.search(r"^:80 \{", caddy, re.M)
    assert "trusted_proxies static {$PM_NET_SUBNET:10.231.3.0/24}" in caddy
    assert "reverse_proxy backend:8000" in caddy
    for header in ("X-Content-Type-Options nosniff", "X-Frame-Options DENY", "Referrer-Policy"):
        assert header in caddy
    assert "SITE_ADDRESS" not in caddy


def test_every_documented_compose_command_passes_the_settings_file():
    for doc in ("docs/DEPLOYMENT.md", "README.md", "deploy/RUNBOOK-PM.md"):
        for line in _read(doc).splitlines():
            command = line.strip()
            if command.startswith("docker compose") and " -p promanage" not in command:
                assert "--env-file" in command, f"{doc}: {command}"
