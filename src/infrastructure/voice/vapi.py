"""
Minimal client for the Vapi REST API (https://docs.vapi.ai), used for voice
role-play. The browser joins the call with the Vapi Web SDK and our public key;
the private key stays here.
"""

from typing import Any

import httpx

from src.core.config import settings

API_URL = "https://api.vapi.ai"


class VapiError(Exception):
    """Vapi is not configured or returned an error."""


class VapiClient:
    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        self.api_key = api_key or settings.VAPI_API_KEY
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _request(
        self, method: str, path: str, json: dict | None = None
    ) -> dict[str, Any]:
        if not self.api_key:
            raise VapiError("Voice role-play is not configured")
        async with httpx.AsyncClient(
            base_url=API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        ) as client:
            response = await client.request(method, path, json=json)
        if response.status_code >= 400:
            raise VapiError(f"Vapi {method} {path} failed: {response.status_code}")
        return response.json() if response.content else {}

    async def create_assistant(self, config: dict[str, Any]) -> str:
        data = await self._request("POST", "/assistant", json=config)
        return data["id"]

    async def delete_assistant(self, assistant_id: str) -> None:
        await self._request("DELETE", f"/assistant/{assistant_id}")

    async def get_call(self, call_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/call/{call_id}")
