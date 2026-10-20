"""Masks secrets in things Eyrie shows or logs: command lines, URLs and MCP targets.

Best effort, by shape: values of secret-named flags and NAME=value pairs, URL passwords and
query values, and strings that look like well-known token formats. The real values are
still what runs; only what people see and what the audit log keeps is masked.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MASK = "***"
SECRET_NAME = re.compile(r"(?i)(token|secret|passw(or)?d|api[-_]?key|apikey|auth|credential|private[-_]?key|access[-_]?key|session|cookie|sig(nature)?)")  # noqa: E501
TOKEN_SHAPES = re.compile(
    r"^(sk-[A-Za-z0-9_-]{16,}|sk_(live|test)_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{16,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$")


def mask_url(url: str) -> str:
    try:
        u = urlsplit(url)
    except ValueError:
        return url
    if not u.scheme or not u.netloc:
        return url
    netloc = u.netloc
    if "@" in netloc:
        userinfo, host = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:{MASK}@{host}" if ":" in userinfo else f"{MASK}@{host}"
    query = urlencode([(k, MASK) for k, _ in parse_qsl(u.query, keep_blank_values=True)], safe="*")
    return urlunsplit((u.scheme, netloc, u.path, query, u.fragment))


def mask_value(v: str) -> str:
    """One argument on its own: a URL, NAME=value, --flag=value, or a bare token."""
    if TOKEN_SHAPES.match(v):
        return MASK
    if "://" in v:
        return mask_url(v)
    name, sep, value = v.partition("=")
    if sep and value and SECRET_NAME.search(name):
        return f"{name}={MASK}"
    return v


def mask_args(args: list[str]) -> list[str]:
    """A command line: also masks the value after a secret-named flag (--api-key X)."""
    out, prev = [], ""
    for a in args:
        if prev.startswith("-") and "=" not in prev and SECRET_NAME.search(prev) and not a.startswith("-"):
            out.append(MASK)
        else:
            out.append(mask_value(a))
        prev = a
    return out
