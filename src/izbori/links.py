"""Links to RIK documents contain Cyrillic. Percent-encode them so they stay valid in any script or file."""

import urllib.parse


def safe_url(url: str) -> str:
    if not url or not url.startswith(("https://", "http://")):
        return ""
    return urllib.parse.quote(url, safe=":/?&=%#@+,;~!$'()*")
