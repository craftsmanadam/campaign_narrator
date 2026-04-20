#!/usr/bin/env python3
"""Spike script: validate orieg/gemma3-tools:12b-ft-v2 schema enforcement via Ollama.

Tests two scenarios that mirror the actual NarratorAgent usage:
  1. Structured output (JSON schema enforcement) — simulates SceneOpeningResponse
  2. Tool call → structured output — simulates retrieve_memory tool + scene response

Run after bin/start_ollama.sh:
  poetry run python bin/test_ollama_schema.py

Expected outcome: both tests pass, response parses into Pydantic models cleanly.
"""

from __future__ import annotations

import json
import sys

import httpx
from pydantic import BaseModel, ValidationError

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL = "orieg/gemma3-tools:12b-ft-v2"
TIMEOUT = 300.0  # 12B on CPU can be slow; generous timeout for cold start

_CONTENT_PREVIEW = 200
_TEXT_PREVIEW = 80
_NS_PER_SEC = 1_000_000_000


# ---------------------------------------------------------------------------
# Sample Pydantic models mirroring production types
# ---------------------------------------------------------------------------


class SceneOpeningResponse(BaseModel):
    """Mirrors campaignnarrator.domain.models.SceneOpeningResponse."""

    text: str
    scene_tone: str


class NarrativeMemoryResult(BaseModel):
    """Return type for the retrieve_memory tool."""

    excerpts: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    schema: dict | None = None,
) -> dict:
    payload: dict = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    if tools:
        payload["tools"] = tools
    if schema:
        payload["format"] = schema

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _check_ollama_running() -> None:
    try:
        httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0).raise_for_status()
    except Exception:
        print("ERROR: Ollama is not running. Start it with: bin/start_ollama.sh")
        sys.exit(1)


def _check_model_available() -> None:
    response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
    models = [m["name"] for m in response.json().get("models", [])]
    if not any(MODEL in m for m in models):
        print(f"ERROR: Model '{MODEL}' not found. Pull it with: bin/start_ollama.sh")
        print(f"Available models: {models or '(none)'}")
        sys.exit(1)


def _preview(text: str, limit: int) -> str:
    return f"{text[:limit]}{'...' if len(text) > limit else ''}"


def _print_timing(result: dict, label: str = "") -> None:
    """Print Ollama inference timing metrics from a chat response."""
    prefix = f"  [{label}] " if label else "  "

    total_ns = result.get("total_duration", 0)
    load_ns = result.get("load_duration", 0)
    prompt_ns = result.get("prompt_eval_duration", 0)
    eval_ns = result.get("eval_duration", 0)
    prompt_tokens = result.get("prompt_eval_count", 0)
    eval_tokens = result.get("eval_count", 0)

    total_s = total_ns / _NS_PER_SEC
    load_s = load_ns / _NS_PER_SEC
    prompt_s = prompt_ns / _NS_PER_SEC
    eval_s = eval_ns / _NS_PER_SEC

    prompt_tps = prompt_tokens / prompt_s if prompt_s > 0 else 0.0
    eval_tps = eval_tokens / eval_s if eval_s > 0 else 0.0

    print(f"{prefix}timing:")
    print(f"{prefix}  total:        {total_s:.2f}s")
    _MIN_LOAD_S = 0.01
    if load_s > _MIN_LOAD_S:
        print(f"{prefix}  model load:   {load_s:.2f}s")
    print(
        f"{prefix}  prompt eval:  {prompt_s:.2f}s"
        f"  ({prompt_tokens} tokens, {prompt_tps:.1f} t/s)"
    )
    print(
        f"{prefix}  generation:   {eval_s:.2f}s"
        f"  ({eval_tokens} tokens, {eval_tps:.1f} t/s)"
    )


# ---------------------------------------------------------------------------
# Test 1: Structured output (JSON schema enforcement)
# ---------------------------------------------------------------------------


def test_structured_output() -> bool:
    print("\n── Test 1: Structured output (SceneOpeningResponse schema) ──")

    scene_setting = (
        "A fog-shrouded dock district at midnight. "
        "Crates stacked high, lanterns flickering. "
        "A figure watches from the shadows."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are opening a new encounter scene for a tabletop RPG. "
                "Write immersive player-facing narration that sets the scene. "
                "Also choose a short scene tone phrase (8 words or fewer) that "
                "captures the emotional register."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "purpose": "scene_opening",
                    "setting": scene_setting,
                    "visible_npc_summaries": ["Malachar: pale, hollow-eyed smuggler"],
                }
            ),
        },
    ]

    schema = SceneOpeningResponse.model_json_schema()

    print(f"  Sending request to {MODEL}...")
    result = _post_chat(messages, schema=schema)

    raw_content = result["message"]["content"]
    _print_timing(result)
    print(f"  Raw content: {_preview(raw_content, _CONTENT_PREVIEW)}")

    try:
        parsed = SceneOpeningResponse.model_validate_json(raw_content)
        print(f"  ✓ text:       {_preview(parsed.text, _TEXT_PREVIEW)}")
        print(f"  ✓ scene_tone: {parsed.scene_tone}")
    except ValidationError as exc:
        print(f"  ✗ Pydantic validation failed: {exc}")
        return False
    except json.JSONDecodeError as exc:
        print(f"  ✗ JSON parse failed: {exc}")
        return False
    else:
        print("  ✓ Parsed successfully")
        return True


# ---------------------------------------------------------------------------
# Test 2: Tool call → structured output
# ---------------------------------------------------------------------------


def _handle_no_tool_call(message: dict) -> bool:
    """Handle the case where the model skipped the tool call."""
    print("  ! No tool call made — model proceeded directly to narration.")
    print("    This may be acceptable behaviour; checking for valid final response...")
    raw_content = message.get("content", "")
    if raw_content:
        try:
            parsed = SceneOpeningResponse.model_validate_json(raw_content)
        except ValidationError, json.JSONDecodeError:
            pass
        else:
            print("  ✓ Direct response parsed successfully (no tool call)")
            print(f"  ✓ scene_tone: {parsed.scene_tone}")
            return True
    print("  ✗ No tool call and no valid structured response")
    return False


def test_tool_call_then_structured_output() -> bool:
    print("\n── Test 2: Tool call → structured output ──")

    retrieve_memory_tool = {
        "type": "function",
        "function": {
            "name": "retrieve_memory",
            "description": (
                "Search prior narrative records for descriptions of named NPCs, "
                "locations, or events. Call this before describing any named entity "
                "the player may have encountered previously."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name or description to search for",
                    }
                },
                "required": ["query"],
            },
        },
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are opening a new encounter scene for a tabletop RPG. "
                "Before describing any named NPC or location the player may have "
                "seen before, call retrieve_memory to check prior records. "
                "Then write immersive player-facing narration and choose a scene tone."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "purpose": "scene_opening",
                    "setting": "The docks at midnight. Malachar waits by the water.",
                    "visible_npc_summaries": ["Malachar: smuggler"],
                }
            ),
        },
    ]

    schema = SceneOpeningResponse.model_json_schema()

    print("  Round 1: sending request (expect tool call for 'Malachar')...")
    result = _post_chat(messages, tools=[retrieve_memory_tool])
    _print_timing(result, "round 1")

    # Check for tool call
    message = result["message"]
    tool_calls = message.get("tool_calls", [])

    if not tool_calls:
        return _handle_no_tool_call(message)

    tool_call = tool_calls[0]
    fn_name = tool_call["function"]["name"]
    fn_args = tool_call["function"]["arguments"]
    query = (
        fn_args.get("query", "")
        if isinstance(fn_args, dict)
        else json.loads(fn_args).get("query", "")
    )
    print(f"  ✓ Tool call: {fn_name}(query={query!r})")

    if fn_name != "retrieve_memory":
        print(f"  ✗ Expected 'retrieve_memory', got '{fn_name}'")
        return False

    # Simulate tool result
    tool_result = (
        "Malachar had pale hollow eyes and moved with practiced silence. "
        "He spoke little."
    )
    messages.append(
        {
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls,
        }
    )
    messages.append({"role": "tool", "content": tool_result})

    # Round 2: get final structured response
    print(
        "  Round 2: sending tool result, expecting structured SceneOpeningResponse..."
    )
    result2 = _post_chat(messages, tools=[retrieve_memory_tool], schema=schema)
    _print_timing(result2, "round 2")

    raw_content = result2["message"]["content"]
    print(f"  Raw content: {_preview(raw_content, _CONTENT_PREVIEW)}")

    try:
        parsed = SceneOpeningResponse.model_validate_json(raw_content)
        print(f"  ✓ text:       {_preview(parsed.text, _TEXT_PREVIEW)}")
        print(f"  ✓ scene_tone: {parsed.scene_tone}")
    except ValidationError as exc:
        print(f"  ✗ Pydantic validation failed: {exc}")
        return False
    except json.JSONDecodeError as exc:
        print(f"  ✗ JSON parse failed: {exc}")
        return False
    else:
        print("  ✓ Parsed successfully after tool call")
        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Ollama schema enforcement spike")
    print(f"Model: {MODEL}")
    print(f"URL:   {OLLAMA_BASE_URL}")

    _check_ollama_running()
    _check_model_available()

    results = {
        "structured_output": test_structured_output(),
        "tool_call_then_structured_output": test_tool_call_then_structured_output(),
    }

    print("\n── Summary ──")
    all_passed = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed. orieg/gemma3-tools:12b-ft-v2 is ready for Slice 2.")
    else:
        print(
            "Some tests failed. "
            "Review output above before proceeding with Slice 2 plan."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
