"""Claude Code OAuth usage endpoint client.

Replicates the CC CLI's `fetchUtilization` call to fetch real Anthropic-side
quota data (5h / 7d windows). Reads the OAuth access token from the macOS
Keychain entry that CC CLI maintains.

Limitations:
  - macOS only (uses `security` command)
  - Depends on undocumented internal endpoint /api/oauth/usage
  - No automatic token refresh; CC CLI keeps the keychain entry fresh
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

import httpx
from pydantic import BaseModel

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_BETA_HEADER = "oauth-2025-04-20"


class WindowUsage(BaseModel):
    utilization: float
    resets_at: Optional[str] = None


class ExtraUsage(BaseModel):
    is_enabled: bool
    monthly_limit: Optional[float] = None
    used_credits: Optional[float] = None
    utilization: Optional[float] = None
    currency: Optional[str] = None


class UsageReport(BaseModel):
    five_hour: WindowUsage
    seven_day: WindowUsage
    seven_day_opus: Optional[WindowUsage] = None
    seven_day_sonnet: Optional[WindowUsage] = None
    seven_day_oauth_apps: Optional[WindowUsage] = None
    seven_day_cowork: Optional[WindowUsage] = None
    seven_day_omelette: Optional[WindowUsage] = None
    extra_usage: Optional[ExtraUsage] = None


class UsageClientError(Exception):
    pass


def _read_access_token() -> str:
    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise UsageClientError(
            f"Cannot read Claude Code credentials from Keychain: {e.stderr.strip()}"
        ) from e
    except FileNotFoundError as e:
        raise UsageClientError(
            "`security` command not found — this feature requires macOS."
        ) from e

    try:
        return json.loads(raw)["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError) as e:
        raise UsageClientError(f"Unexpected keychain payload shape: {e}") from e


async def fetch_usage() -> UsageReport:
    token = _read_access_token()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": OAUTH_BETA_HEADER,
            },
        )
    if r.status_code == 401:
        raise UsageClientError(
            "OAuth token rejected. Run `claude auth login` to refresh credentials."
        )
    r.raise_for_status()
    return UsageReport.model_validate(r.json())
