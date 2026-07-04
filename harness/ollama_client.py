"""Thin HTTP client for Ollama's /api/chat with native tool calling.

Infrastructure retries (connection blips) are separated from *agent* behavior:
they are logged as `infra_retries` and never shown to the model, so they can't
contaminate the failure-mode analysis.
"""

import time

import requests

INFRA_RETRIES = 3
CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 900


class OllamaClient:
    def __init__(self, base_url: str, keep_alive: str = "30m"):
        self.base_url = base_url.rstrip("/")
        self.keep_alive = keep_alive
        self.session = requests.Session()

    def chat(self, model: str, messages: list[dict], tools: list[dict],
             options: dict) -> tuple[dict, int]:
        """Returns (response_json, infra_retries_used)."""
        payload = {"model": model, "messages": messages, "tools": tools,
                   "options": options, "stream": False,
                   "keep_alive": self.keep_alive}
        last_exc = None
        for attempt in range(INFRA_RETRIES + 1):
            try:
                r = self.session.post(f"{self.base_url}/api/chat", json=payload,
                                      timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S))
                r.raise_for_status()
                return r.json(), attempt
            except (requests.ConnectionError, requests.Timeout,
                    requests.HTTPError) as exc:
                last_exc = exc
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Ollama unreachable after {INFRA_RETRIES + 1} "
                           f"attempts: {last_exc}")

    def show(self, model: str) -> dict:
        """Model metadata (incl. digest/quantization) for the run manifest."""
        r = self.session.post(f"{self.base_url}/api/show",
                              json={"model": model}, timeout=(10, 60))
        r.raise_for_status()
        details = r.json().get("details", {})
        digest = ""
        try:  # digests live in the /api/tags listing, not /api/show
            tags = self.session.get(f"{self.base_url}/api/tags",
                                    timeout=(10, 60)).json()
            digest = next((m.get("digest", "") for m in tags.get("models", [])
                           if m.get("name") == model
                           or m.get("model") == model), "")
        except requests.RequestException:
            pass
        return {"model": model,
                "digest": digest,
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level")}
