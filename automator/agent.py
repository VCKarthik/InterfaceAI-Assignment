"""Choose one browser action at a time using the configured model."""
import json
import os
from dataclasses import dataclass

import httpx

from .models import AgentChoice

SYSTEM = """You operate a local SYNTHETIC legacy banking UI using structured, single-step actions.
Your goal is to retrieve CURRENT SAVINGS BALANCE AND ACCOUNT STATUS of the member.
Choose a single action grounded in current observed page text and controls.
Supported actions: fill, click, extract, finish. Supported kinds: role, label, text, table_row, none.
For a textbox enter member ID, use action=fill, kind=label, name='Member ID', value='{{member_id}}'.
For links/buttons use kind=role, role='link'/'button', name EXACTLY as shown.
To extract the balance: action=extract, kind=table_row, name='Current Balance', output_key='balance'.
To extract status: action=extract, kind=table_row, name='Status', output_key='account_status'.
After BOTH extracts, choose finish. Never finish unless both are extracted.
Never write raw IDs or balances into your rationale. Never navigate outside localhost.
All unused string fields must be empty strings. Never request financial changes."""

AGENT_CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["fill", "click", "extract", "finish"]},
        "kind": {"type": "string", "enum": ["role", "label", "text", "table_row", "none"]},
        "name": {"type": "string"},
        "role": {"type": "string"},
        "value": {"type": "string"},
        "output_key": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["action", "kind", "name", "role", "value", "output_key", "rationale"],
}


@dataclass
class LlmClient:
    provider: str
    client: object = None
    api_key: str = ""


def configured_client_and_model() -> tuple[LlmClient, str]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not provider:
        provider = "gemini" if os.getenv("GEMINI_API_KEY") else "openai"

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or api_key == "replace_me":
            raise RuntimeError("GEMINI_API_KEY must be set in .env for Gemini discovery")
        return LlmClient(provider="gemini", api_key=api_key), os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    if provider == "openai":
        from openai import OpenAI

        return LlmClient(provider="openai", client=OpenAI()), os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")


def _prompt(goal: str, observation: dict, history: list[dict], outputs: dict) -> str:
    return json.dumps({
        "goal": goal,
        "current_observation": observation,
        "completed_actions": history[-15:],
        "outputs_obtained": list(outputs.keys()),
        "your_task": "Choose ONLY the next grounded action for this page.",
    })


def _decide_gemini(client: LlmClient, model: str, prompt: str) -> AgentChoice:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseFormat": {
                "text": {
                    "mimeType": "application/json",
                    "schema": AGENT_CHOICE_SCHEMA,
                }
            },
        },
    }
    legacy_payload = {
        "systemInstruction": payload["systemInstruction"],
        "contents": payload["contents"],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": AGENT_CHOICE_SCHEMA,
        },
    }
    with httpx.Client(timeout=60) as http:
        response = http.post(
            url,
            headers={"x-goog-api-key": client.api_key, "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code == 400 and "response_format" in response.text:
            response = http.post(
                url,
                headers={"x-goog-api-key": client.api_key, "Content-Type": "application/json"},
                json=legacy_payload,
            )
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text[:500]}")
    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Gemini response did not include structured text: {data}") from e
    return AgentChoice.model_validate_json(text)


def _decide_openai(client: LlmClient, model: str, prompt: str) -> AgentChoice:
    response = client.client.responses.parse(
        model=model,
        instructions=SYSTEM,
        input=prompt,
        text_format=AgentChoice,
    )
    if response.output_parsed is None:
        raise RuntimeError("Model returned no valid structured action")
    return response.output_parsed


def decide(client: LlmClient, model: str, goal: str, observation: dict, history: list[dict], outputs: dict) -> AgentChoice:
    prompt = _prompt(goal, observation, history, outputs)
    if client.provider == "gemini":
        return _decide_gemini(client, model, prompt)
    return _decide_openai(client, model, prompt)
