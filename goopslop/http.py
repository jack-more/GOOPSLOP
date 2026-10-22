"""Tiny stdlib HTTP helper with backoff, so the tool has no dependencies."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Metacritic's backend rejects non-browser user agents.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) goopslop/0.1"
RETRYABLE = {429, 500, 502, 503, 504}


def get_json(url, params=None, retries=5, timeout=30):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code not in RETRYABLE or attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2**attempt)
