"""One-time additions to existing, teacher-editable app lists."""
from urllib.parse import urlsplit

from config import APP_LINK_UPDATES, DEFAULT_SETTINGS


UPDATE_SETTING = "tool_apps_updated_20261019"


def _url_key(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, parts.fragment)


def updated_app_links(raw):
    """Keep other apps and their order; update requested URLs once each."""
    requested = {_url_key(url): (name, url) for name, url in APP_LINK_UPDATES}
    found, lines = set(), []
    for line in (raw if raw.strip() else DEFAULT_SETTINGS["tool_apps"]).splitlines():
        if not line.strip():
            continue
        name, url = line.split("|", 1) if "|" in line else (line, line)
        name, url = name.strip(), url.strip()
        key = _url_key(url)
        if key in requested:
            if key in found:
                continue
            found.add(key)
            name, url = requested[key]
        lines.append(f"{name}|{url}")
    lines.extend(f"{name}|{url}" for name, url in APP_LINK_UPDATES if _url_key(url) not in found)
    return "\n".join(lines)
