"""Composio OAuth callback HTML response (popup close helper)."""

from __future__ import annotations

from starlette.responses import HTMLResponse


def oauth_callback_html(*, success: bool) -> HTMLResponse:
    message = (
        "Authorization complete. You can close this window."
        if success
        else "Authorization failed."
    )
    html = f"""<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>Composio authorization</title></head>
  <body style="font-family: system-ui, sans-serif; padding: 24px; text-align: center;">
    <p>{message}</p>
    <script>
      (function () {{
        setTimeout(function () {{ window.close(); }}, 300);
      }})();
    </script>
  </body>
</html>"""
    return HTMLResponse(html, headers={"content-type": "text/html; charset=utf-8"})
