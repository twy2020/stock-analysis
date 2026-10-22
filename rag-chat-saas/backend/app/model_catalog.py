from __future__ import annotations

from datetime import datetime, timezone
import re

import httpx
from bs4 import BeautifulSoup


REFERENCE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
EXCLUDED_TERMS = (
    "embedding", "embed", "rerank", "ranker", "re-rank", "whisper", "transcri",
    "tts", "speech", "audio", "image", "dall-e", "flux", "stable-diffusion",
    "video", "moderation", "guard", "ocr", "vision-encoder",
)


def chat_model(row: dict) -> bool:
    model_id = row.get("id")
    if not isinstance(model_id, str) or not model_id or len(model_id) > 200:
        return False
    kind = str(row.get("type") or row.get("model_type") or row.get("mode") or "").lower()
    if kind in {"embedding", "rerank", "image", "audio", "video", "moderation"}:
        return False
    return not any(term in model_id.lower() for term in EXCLUDED_TERMS)


def reference_price(provider_type: str, model_id: str, catalog: dict) -> dict | None:
    if provider_type not in {"OPENAI", "DEEPSEEK"}:
        return None
    key = f"deepseek/{model_id}" if provider_type == "DEEPSEEK" else model_id
    item = catalog.get(key) or (catalog.get(model_id) if provider_type == "DEEPSEEK" else None)
    expected = "openai" if provider_type == "OPENAI" else "deepseek"
    if not isinstance(item, dict) or item.get("litellm_provider") != expected or item.get("mode") != "chat":
        return None
    input_cost, output_cost = item.get("input_cost_per_token"), item.get("output_cost_per_token")
    if not isinstance(input_cost, (float, int)) or not isinstance(output_cost, (float, int)):
        return None
    return {"currency": "USD", "inputPerMillion": round(input_cost * 1_000_000, 6),
            "outputPerMillion": round(output_cost * 1_000_000, 6), "source": "LiteLLM reference"}


def siliconflow_prices(html: str) -> dict[str, dict]:
    result = {}
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select('div[id^="pricing-row-text-"]'):
        cells = row.find_all("div", recursive=False)
        if len(cells) < 4 or (len(cells) - 1) % 3:
            continue
        link = cells[0].find("a", title=True)
        if link is None:
            continue
        values = []
        for cell in cells[1:]:
            raw = cell.get_text(" ", strip=True)
            amounts = re.findall(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", raw)
            values.append(float(amounts[0]) if len(amounts) == 1 else 0.0 if raw == "免费" else None)
        inputs, outputs = values[0::3], values[1::3]
        if None in inputs or None in outputs or len(set(inputs)) != 1 or len(set(outputs)) != 1:
            continue
        result[link["title"]] = {"currency": "CNY", "inputPerMillion": inputs[0],
                                  "outputPerMillion": outputs[0], "source": "SiliconFlow official"}
    return result


def discover_models(provider_type: str, base_url: str, api_key: str) -> dict:
    response = httpx.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"},
                         timeout=12, follow_redirects=False)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Invalid model catalog")
    rows = [row for row in data["data"][:1000] if isinstance(row, dict) and chat_model(row)]
    reference: dict = {}
    if provider_type in {"OPENAI", "DEEPSEEK", "SILICONFLOW"}:
        try:
            price_url = "https://www.siliconflow.cn/pricing" if provider_type == "SILICONFLOW" else REFERENCE_URL
            price_response = httpx.get(price_url, timeout=8, follow_redirects=False)
            price_response.raise_for_status()
            payload = siliconflow_prices(price_response.text) if provider_type == "SILICONFLOW" else price_response.json()
            if isinstance(payload, dict):
                reference = payload
        except (httpx.HTTPError, ValueError):
            pass
    return {"models": [{"id": row["id"], "price": reference.get(row["id"]) if provider_type == "SILICONFLOW"
                       else reference_price(provider_type, row["id"], reference)}
                       for row in rows], "fetchedAt": datetime.now(timezone.utc).isoformat()}


def normalized_price(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("currency") not in {"USD", "CNY"} \
            or value.get("source") not in {"manual", "LiteLLM reference", "SiliconFlow official"}:
        raise ValueError("Invalid price")
    for key in ("inputPerMillion", "outputPerMillion"):
        number = value.get(key)
        if not isinstance(number, (int, float)) or isinstance(number, bool) or not 0 <= number <= 1_000_000:
            raise ValueError("Invalid price")
    return {"currency": value["currency"], "inputPerMillion": value["inputPerMillion"],
            "outputPerMillion": value["outputPerMillion"], "source": value["source"]}
