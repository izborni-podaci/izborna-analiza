"""Project-wide settings. Override with environment variables when running a fork."""

import os

SITE_URL = os.environ.get("IZBORI_SITE_URL", "https://izborni-podaci.github.io/izborna-analiza/").rstrip("/") + "/"
REPO_URL = os.environ.get("IZBORI_REPO_URL", "https://github.com/izborni-podaci/izborna-analiza")
RIK_BASE = os.environ.get("IZBORI_RIK_BASE", "https://www.rik.parlament.gov.rs")
RIK_PUBLIC = "https://www.rik.parlament.gov.rs"
USER_AGENT = f"izborni-podaci/0.1 (+{REPO_URL})"
