"""Restrict automation to the local bank and permitted read-only actions."""
from urllib.parse import urljoin, urlparse


class PolicyError(Exception):
    pass


class Policy:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        p = urlparse(self.base_url)
        if p.scheme != "http" or p.hostname not in {"127.0.0.1", "localhost"}:
            raise PolicyError("Only a localhost synthetic demo target is allowed")
        self.origin = (p.scheme, p.netloc)

    def check_url(self, url: str):
        p = urlparse(urljoin(self.base_url + "/", url))
        if (p.scheme, p.netloc) != self.origin:
            raise PolicyError("Domain outside allowlist")
        if not (p.path == "/servicing" or p.path == "/members/search" or p.path.startswith("/members/")):
            raise PolicyError("Route outside allowlist")

    def check_step(self, action: str, target_name: str):
        if action not in {"fill", "click", "extract", "finish"}:
            raise PolicyError("Action outside allowlist")
        if any(word in target_name.lower() for word in ("transfer", "wire", "delete", "close account")):
            raise PolicyError("Potentially irreversible action blocked")
