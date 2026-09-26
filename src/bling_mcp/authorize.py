"""One-time OAuth 2.0 authorization-code helper for Bling.

Use this once to obtain the ``BLING_REFRESH_TOKEN`` the server runs on:

    python -m bling_mcp.authorize url --client-id YOUR_ID
    # open the printed URL, approve, copy the `code` from the redirect, then:
    python -m bling_mcp.authorize exchange --client-id YOUR_ID \
        --client-secret YOUR_SECRET --code THE_CODE --refresh-only
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any, Sequence
from urllib.parse import urlencode

import httpx

from .auth import AuthError
from .config import DEFAULT_TOKEN_URL

DEFAULT_AUTHORIZE_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"


def build_authorize_url(
    client_id: str,
    *,
    state: str = "bling-mcp",
    redirect_uri: str | None = None,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """Build the browser URL the user visits to grant access."""
    params = {"response_type": "code", "client_id": client_id, "state": state}
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    return f"{authorize_url}?{urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    http_client: httpx.Client,
    *,
    token_url: str = DEFAULT_TOKEN_URL,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code for the token set (incl. refresh_token).

    ``redirect_uri`` must be repeated here when it was sent in the authorize
    request (RFC 6749 §4.1.3); the CLI bootstrap never sends one.
    """
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = {"grant_type": "authorization_code", "code": code}
    if redirect_uri:
        data["redirect_uri"] = redirect_uri
    try:
        response = http_client.post(
            token_url,
            data=data,
            headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise AuthError(f"Authorization code exchange failed: {exc}") from exc

    if not response.is_success:
        raise AuthError(
            "Authorization code exchange failed: "
            f"HTTP {response.status_code} {response.text}"
        )
    return response.json()


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m bling_mcp.authorize",
        description="Bling OAuth 2.0 helper (one-time refresh-token bootstrap).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_url = sub.add_parser("url", help="print the authorization URL to open")
    p_url.add_argument("--client-id", default=os.environ.get("BLING_CLIENT_ID"))
    p_url.add_argument("--state", default="bling-mcp")
    p_url.add_argument("--redirect-uri", default=None)

    p_ex = sub.add_parser("exchange", help="exchange an authorization code for tokens")
    p_ex.add_argument("--code", required=True)
    p_ex.add_argument("--client-id", default=os.environ.get("BLING_CLIENT_ID"))
    p_ex.add_argument("--client-secret", default=os.environ.get("BLING_CLIENT_SECRET"))
    p_ex.add_argument(
        "--refresh-only",
        action="store_true",
        help="print only the refresh token (handy for scripts)",
    )

    args = parser.parse_args(argv)

    if args.command == "url":
        if not args.client_id:
            parser.error("client id required (set BLING_CLIENT_ID or pass --client-id)")
        print(
            build_authorize_url(
                args.client_id, state=args.state, redirect_uri=args.redirect_uri
            )
        )
        return 0

    # command == "exchange"
    if not args.client_id or not args.client_secret:
        parser.error(
            "client id and secret required "
            "(set BLING_CLIENT_ID/BLING_CLIENT_SECRET or pass flags)"
        )
    with httpx.Client(timeout=30.0) as http:
        payload = exchange_code(args.client_id, args.client_secret, args.code, http)
    if args.refresh_only:
        print(payload.get("refresh_token", ""))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
