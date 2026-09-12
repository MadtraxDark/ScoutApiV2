"""Open a headed Camoufox window to seed the persistent browser profile.

Use this once (or when Shopee trust expires) so Docker scrapes reuse cookies /
device binding for signed ``get_pc`` calls.

Google SSO often freezes or is blocked inside automated browsers. Prefer
Shopee email/password (or phone) login when seeding.

Example:
    python scripts/seed_camoufox_profile.py --login
    python scripts/seed_camoufox_profile.py --url https://shopee.com.br/...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scout_api.core.config import get_settings  # noqa: E402
from scout_api.modules.crawler.services.html_fetcher import (  # noqa: E402
    apply_shopee_br_proxy_targeting,
    proxy_settings_from_url,
)

DEFAULT_URL = "https://shopee.com.br/"
LOGIN_URL = "https://shopee.com.br/buyer/login"
HOST_PROFILES_ROOT = ROOT / "data" / "camoufox-profiles"
HOST_PROFILE_DIR = HOST_PROFILES_ROOT / "default"


def _profile_dir(configured: str | None) -> Path:
    """Prefer the Compose bind-mount path under ./data when unset."""
    if configured and configured.strip():
        path = Path(configured.strip())
        posix = path.as_posix()
        if posix.startswith("/home/app/.cache/scout-api/camoufox-profiles"):
            return HOST_PROFILE_DIR
        return path
    return HOST_PROFILE_DIR


def _first_page(browser: Any) -> Any:
    pages = list(getattr(browser, "pages", None) or [])
    page = pages[0] if pages else browser.new_page()
    for extra in pages[1:]:
        try:
            extra.close()
        except Exception:
            pass
    return page


def _attach_popup_handler(browser: Any) -> None:
    """Bring OAuth popups to the front instead of leaving them hung in the background."""

    def on_page(new_page: Any) -> None:
        try:
            url = str(getattr(new_page, "url", "") or "")
            print(f"\nPopup/aba nova: {url or '(carregando…)'}")
            print(
                "Se for login Google: complete NA POPUP. "
                "Se travar/bloquear, feche e use e-mail/senha da Shopee."
            )
            bring = getattr(new_page, "bring_to_front", None)
            if callable(bring):
                bring()
        except Exception:
            pass

    on_fn = getattr(browser, "on", None)
    if callable(on_fn):
        on_fn("page", on_page)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Camoufox persistent profile (headed) for Shopee/WAF."
    )
    parser.add_argument(
        "--url",
        default=None,
        help=f"Start URL (default: home, or login page with --login)",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help=f"Open {LOGIN_URL} (prefer e-mail/senha; avoid Google SSO).",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Ignore CAMOUFOX_PROXY_URL (not recommended for Shopee).",
    )
    parser.add_argument(
        "--humanize",
        action="store_true",
        help="Enable Camoufox humanize (can freeze Google OAuth; off by default).",
    )
    args = parser.parse_args()
    start_url = args.url or (LOGIN_URL if args.login else DEFAULT_URL)

    settings = get_settings()
    profile = _profile_dir(settings.camoufox_user_data_dir)
    profile.mkdir(parents=True, exist_ok=True)

    proxy_url = None if args.no_proxy else settings.camoufox_proxy_url
    # humanize off by default: OAuth popups / Google often hang with it on.
    launch: dict[str, Any] = {
        "headless": False,
        "humanize": bool(args.humanize),
        "os": "windows",
        "geoip": False,
        "persistent_context": True,
        "user_data_dir": str(profile),
        "locale": "pt-BR",
        # Allow Google/Shopee OAuth popups.
        "firefox_user_prefs": {
            "dom.disable_open_during_load": False,
            "dom.block_multiple_popups": False,
            "privacy.popups.disable_from_plugins": 0,
        },
    }
    if proxy_url:
        targeted = apply_shopee_br_proxy_targeting(proxy_url, start_url)
        launch["proxy"] = proxy_settings_from_url(targeted)
        print(f"Proxy: {launch['proxy']['server']} (geo BR applied when Shopee)")
    else:
        print("WARNING: CAMOUFOX_PROXY_URL empty — Shopee may block immediately.")

    try:
        from camoufox.addons import DefaultAddons
        from camoufox.sync_api import Camoufox

        launch["exclude_addons"] = [DefaultAddons.UBO]
    except ImportError as exc:
        print(
            "camoufox is required. Run: pip install -e . && python -m camoufox fetch",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    print(f"Profile: {profile}")
    print(f"Opening: {start_url}")
    print()
    print("IMPORTANTE — login Shopee:")
    print("  • Prefira e-mail/senha ou telefone (NÃO Google).")
    print("  • Google SSO costuma travar/bloquear no Camoufox.")
    print("  • Se uma popup abrir, use essa janela; depois volte aqui.")
    print()
    print("Depois do login: abra um produto, volte ao terminal, Enter.")

    try:
        with Camoufox(**launch) as browser:  # type: ignore[no-untyped-call]
            _attach_popup_handler(browser)
            page = _first_page(browser)
            page.goto(start_url, wait_until="domcontentloaded")
            try:
                input("\nPress Enter to save profile and exit… ")
            except EOFError:
                page.wait_for_timeout(300_000)
            except KeyboardInterrupt:
                print("\nInterrupted; saving profile…")
    except Exception as exc:
        if type(exc).__name__ != "TargetClosedError":
            raise
        print("Browser already closed; profile should still be on disk.")

    print(f"Profile saved at {profile}")
    print("Restart API: docker compose up -d api")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
