"""Provider-neutral tool-calling conversation format and converters."""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AssistantTurn:
    text: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "end_turn"  # tool_use | end_turn | max_tokens
    raw_provider_content: Any = None


def assistant_message_from_turn(turn: AssistantTurn) -> dict:
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": turn.text or "",
        "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls],
    }
    if turn.raw_provider_content is not None:
        msg["_raw_content"] = turn.raw_provider_content
    return msg


def tool_results_message(results) -> dict:
    items = []
    for call_id, name, result in results:
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        items.append({"id": call_id, "name": name, "content": content})
    return {"role": "user", "tool_results": items}


def neutral_to_anthropic_messages(messages: list[dict]) -> list:
    out = []
    for m in messages:
        if m.get("tool_results"):
            out.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                    for r in m["tool_results"]
                ],
            })
        elif m.get("role") == "assistant":
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("arguments") or {}})
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    return out


def neutral_to_openai_messages(messages: list[dict]) -> list:
    out = []
    for m in messages:
        if m.get("tool_results"):
            for r in m["tool_results"]:
                out.append({"role": "tool", "tool_call_id": r["id"], "content": r["content"]})
        elif m.get("role") == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            calls = m.get("tool_calls") or []
            if calls:
                msg["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                    for c in calls
                ]
            out.append(msg)
        else:
            out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    return out


def neutral_to_gemini_contents(messages: list[dict]) -> list:
    from google.genai import types

    out = []
    for m in messages:
        if m.get("tool_results"):
            parts = [
                types.Part.from_function_response(name=r["name"], response={"result": r["content"]})
                for r in m["tool_results"]
            ]
            out.append(types.Content(role="user", parts=parts))
        elif m.get("role") == "assistant":
            if m.get("_raw_content") is not None:
                out.append(m["_raw_content"])
                continue
            parts = []
            if m.get("content"):
                parts.append(types.Part(text=m["content"]))
            for c in m.get("tool_calls") or []:
                parts.append(types.Part(function_call=types.FunctionCall(name=c["name"], args=c.get("arguments") or {})))
            if not parts:
                parts.append(types.Part(text=""))
            out.append(types.Content(role="model", parts=parts))
        else:
            out.append(types.Content(role="user", parts=[types.Part(text=m.get("content") or "")]))
    return out


_EMPTY_OBJECT_SCHEMA = {"type": "object", "properties": {}}


def openai_tools_to_anthropic(tools: list[dict]) -> list:
    out = []
    for t in tools or []:
        fn = t.get("function", t)
        out.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or dict(_EMPTY_OBJECT_SCHEMA),
        })
    return out


_GEMINI_TYPES = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _to_gemini_schema(schema: dict):
    from google.genai import types

    schema = schema or {}
    kwargs: dict[str, Any] = {"type": _GEMINI_TYPES.get(str(schema.get("type", "object")).lower(), "STRING")}
    if schema.get("description"):
        kwargs["description"] = schema["description"]
    if isinstance(schema.get("properties"), dict):
        kwargs["properties"] = {k: _to_gemini_schema(v) for k, v in schema["properties"].items()}
    if schema.get("required"):
        kwargs["required"] = list(schema["required"])
    if isinstance(schema.get("items"), dict):
        kwargs["items"] = _to_gemini_schema(schema["items"])
    if schema.get("enum"):
        kwargs["enum"] = [str(v) for v in schema["enum"]]
    return types.Schema(**kwargs)


def openai_tools_to_gemini(tools: list[dict]):
    from google.genai import types

    decls = []
    for t in tools or []:
        fn = t.get("function", t)
        decls.append(types.FunctionDeclaration(
            name=fn["name"],
            description=fn.get("description", ""),
            parameters=_to_gemini_schema(fn.get("parameters") or dict(_EMPTY_OBJECT_SCHEMA)),
        ))
    return decls
