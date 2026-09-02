#!/usr/bin/env python3
"""Local LLM Adapter Proxy simulator for Gemini protocol.

Accepts Gemini-format requests and forwards to either:
  - Vertex AI backend (--auth adc, requires project/location)
  - Generative Language API (--auth api-key, requires --api-key)

Usage:
    python llm_adapter_proxy.py --port 8080 --auth adc --project cloud-llm-preview1 --location global
    python llm_adapter_proxy.py --port 8080 --auth api-key --api-key AIzaSy...
"""

import argparse
import asyncio
import json
import logging

import google.auth
import google.auth.transport.requests
from aiohttp import web, ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def get_adc_credentials():
    """Get ADC credentials (from gcloud auth application-default login)."""
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    log.info("ADC identity: %s (project: %s)", getattr(creds, 'service_account_email', getattr(creds, '_subject', 'user')), project)
    return creds


class GeminiProxy:
    def __init__(self, auth_mode: str, project: str = "", location: str = "", api_key: str = ""):
        self.auth_mode = auth_mode
        self.project = project
        self.location = location
        self.api_key = api_key
        self.session: ClientSession | None = None
        self._creds = None

        if auth_mode == "adc":
            if location == "global":
                self.backend = "https://aiplatform.googleapis.com"
            else:
                self.backend = f"https://{location}-aiplatform.googleapis.com"
        else:
            self.backend = "https://generativelanguage.googleapis.com"

    async def start(self):
        self.session = ClientSession(timeout=ClientTimeout(total=300))
        if self.auth_mode == "adc":
            self._creds = get_adc_credentials()
            log.info("ADC token acquired (expires: %s)", self._creds.expiry)
        else:
            log.info("Using API key: %s...%s", self.api_key[:10], self.api_key[-4:])

    async def stop(self):
        if self.session:
            await self.session.close()

    def _get_auth_headers(self) -> dict:
        if self.auth_mode == "adc":
            if not self._creds.valid:
                self._creds.refresh(google.auth.transport.requests.Request())
                log.info("ADC token refreshed (expires: %s)", self._creds.expiry)
            return {"Authorization": f"Bearer {self._creds.token}"}
        return {}

    def _build_backend_url(self, model: str, method: str, query_string: str) -> str:
        if self.auth_mode == "adc":
            url = (
                f"{self.backend}/v1beta1/projects/{self.project}"
                f"/locations/{self.location}"
                f"/publishers/google/models/{model}:{method}"
            )
        else:
            url = f"{self.backend}/v1beta/models/{model}:{method}"
            qs_parts = []
            if query_string:
                qs_parts.append(query_string)
            qs_parts.append(f"key={self.api_key}")
            return url + "?" + "&".join(qs_parts)

        if query_string:
            url += f"?{query_string}"
        return url

    async def handle_generate(self, request: web.Request) -> web.StreamResponse:
        """Handle both streamGenerateContent and generateContent."""
        model = request.match_info["model"]
        method = request.match_info["method"]

        is_stream = method == "streamGenerateContent"

        body = await request.read()
        backend_url = self._build_backend_url(model, method, request.query_string)

        log.info("→ %s %s (model=%s, stream=%s, %d bytes)",
                 request.method, backend_url, model, is_stream, len(body))

        headers = {"Content-Type": "application/json", **self._get_auth_headers()}

        try:
            async with self.session.post(backend_url, data=body, headers=headers) as resp:
                return await self._forward_response(resp, is_stream)

        except Exception as e:
            log.error("Backend error: %s", e)
            return web.json_response(
                {"error": {"message": str(e), "type": "api_error"}},
                status=500,
            )

    async def _forward_response(self, resp, is_stream: bool) -> web.StreamResponse:
        """Forward backend response to client, streaming if needed."""
        if resp.status != 200:
            error_body = await resp.text()
            log.error("← %d: %s", resp.status, error_body[:200])
            return web.Response(
                status=resp.status,
                content_type=resp.content_type,
                body=error_body,
            )

        if is_stream:
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            await response.prepare(resp._request if hasattr(resp, '_request') else None)

            # We need the original aiohttp request to prepare the response.
            # Since we can't easily get it here, return a different way.
            raise NotImplementedError("Use handle_generate directly for streaming")

        body = await resp.read()
        log.info("← 200 (%d bytes)", len(body))
        return web.Response(
            status=200,
            content_type="application/json",
            body=body,
        )

    async def handle_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle streaming requests with SSE passthrough."""
        model = request.match_info["model"]
        method = request.match_info["method"]
        is_stream = method == "streamGenerateContent"

        body = await request.read()
        backend_url = self._build_backend_url(model, method, request.query_string)

        log.info("→ POST %s (model=%s, stream=%s, %d bytes)",
                 backend_url, model, is_stream, len(body))

        adapter_source = request.headers.get("x-adapter-source", "")
        sso_email = request.headers.get("sso-email", "")
        api_key_header = request.headers.get("x-goog-api-key", "")
        log.info("  Gateway headers: x-adapter-source=%s, sso-email=%s", adapter_source, sso_email)
        if api_key_header:
            log.info("  x-goog-api-key present (IGNORED by gateway, using proxy's own key)")
        else:
            log.info("  x-goog-api-key absent (gateway auth via custom headers)")

        headers = {"Content-Type": "application/json", **self._get_auth_headers()}

        try:
            resp = await self.session.post(backend_url, data=body, headers=headers)

            if resp.status != 200:
                error_body = await resp.text()
                log.error("← %d: %s", resp.status, error_body[:500])
                return web.Response(
                    status=resp.status,
                    content_type=resp.content_type or "application/json",
                    body=error_body,
                )

            if is_stream:
                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": resp.content_type or "text/event-stream",
                        "Cache-Control": "no-cache",
                    },
                )
                await response.prepare(request)

                async for chunk in resp.content.iter_any():
                    await response.write(chunk)

                await response.write_eof()
                log.info("← 200 (stream complete)")
                return response
            else:
                body = await resp.read()
                log.info("← 200 (%d bytes)", len(body))
                return web.Response(
                    status=200,
                    content_type="application/json",
                    body=body,
                )

        except Exception as e:
            log.error("Backend error: %s", e)
            return web.json_response(
                {"error": {"message": str(e), "type": "api_error"}},
                status=500,
            )

    async def handle_models(self, request: web.Request) -> web.Response:
        """Handle GET /v1beta/models — list available models."""
        if self.auth_mode == "adc":
            backend_url = (
                f"{self.backend}/v1beta1/projects/{self.project}"
                f"/locations/{self.location}/publishers/google/models"
            )
        else:
            backend_url = f"{self.backend}/v1beta/models?key={self.api_key}"
        headers = {**self._get_auth_headers()}

        log.info("→ GET %s", backend_url)
        try:
            async with self.session.get(backend_url, headers=headers) as resp:
                body = await resp.text()
                log.info("← %d (%d bytes)", resp.status, len(body))
                return web.Response(
                    status=resp.status,
                    content_type="application/json",
                    body=body,
                )
        except Exception as e:
            log.error("Backend error: %s", e)
            return web.json_response(
                {"error": {"message": str(e), "type": "api_error"}},
                status=500,
            )


def main():
    parser = argparse.ArgumentParser(description="Local LLM Adapter Proxy for Gemini")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--auth", choices=["adc", "api-key"], default="adc", help="Auth mode")
    parser.add_argument("--project", default="agolis-allen-first", help="GCP project ID (adc mode)")
    parser.add_argument("--location", default="global", help="GCP location (adc mode)")
    parser.add_argument("--api-key", default="", help="Gemini API key (api-key mode)")
    args = parser.parse_args()

    if args.auth == "api-key" and not args.api_key:
        parser.error("--api-key is required when --auth api-key")

    proxy = GeminiProxy(
        auth_mode=args.auth,
        project=args.project,
        location=args.location,
        api_key=args.api_key,
    )

    app = web.Application()

    # Gemini API routes (matching XHS LLM Adapter Step 2 format)
    # POST /v1beta/models/{model}:streamGenerateContent
    # POST /v1beta/models/{model}:generateContent
    app.router.add_post("/v1beta/models/{model}:{method}", proxy.handle_stream)

    # GET /v1beta/models — list models
    app.router.add_get("/v1beta/models", proxy.handle_models)

    # Health check
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    async def on_startup(app):
        await proxy.start()
        log.info("Gemini proxy started on port %d (auth=%s)", args.port, args.auth)
        if args.auth == "adc":
            log.info("Backend: %s (project=%s, location=%s)", proxy.backend, args.project, args.location)
        else:
            log.info("Backend: %s (api-key)", proxy.backend)
        log.info("")
        log.info("Endpoints:")
        log.info("  POST http://localhost:%d/v1beta/models/{model}:generateContent", args.port)
        log.info("  POST http://localhost:%d/v1beta/models/{model}:streamGenerateContent?alt=sse", args.port)
        log.info("  GET  http://localhost:%d/v1beta/models", args.port)

    async def on_cleanup(app):
        await proxy.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(app, host="0.0.0.0", port=args.port, print=None)


if __name__ == "__main__":
    main()
