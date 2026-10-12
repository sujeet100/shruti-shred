"""
The native Gemini provider, asking only for the fields that carry information.

CrewAI 1.15.2 builds every structured-output schema for OpenAI's strict mode — including
`ensure_all_properties_required`, which marks EVERY property required — and sends that same
schema to Gemini. Gemini does not need it, but it obeys it: each lead note came back with all ten
fields, defaults and nulls included (`"grace":[],"meend_swara":null,"rest":false,...`) — 148
characters a note where `{"swara":"G","dur":1.0}` says it all. Notes were 95% of the lead's
output, and output tokens are what the run waits on (trace 15fbd6571f72: 52k lead output tokens).

`lean_schema` is CrewAI's own pipeline minus that one step, so `required` stays what the Pydantic
model declares (a note needs only its swara and duration) and our models fill every default when
the response is parsed. Two more hints had to go, measured live (2026-10-12): with only `required`
relaxed the model still wrote every key, because each optional field carried `"default": null`
and every nested object a `propertyOrdering` listing all ten keys. So defaults are stripped and
the ordering is kept only at the TOP level, where it puts `phrase_plan` before `notes` (reasoning
first). Re-check on a CrewAI upgrade.

Scoped to the objects where the waste is (`LEAN_OBJECTS`): the NOTES (95% of the output) and the
phrase plan, whose optional fields the prompt says to omit outside a taan or alap. Every other
object — a chart's sections, a verdict — stays fully required, as CrewAI sends it: there a field
is optional only because it has a default, and the prompts expect it filled.
"""

from __future__ import annotations

from typing import Any

from crewai.llms.providers.gemini.completion import GeminiCompletion
from crewai.utilities.pydantic_schema_utils import (
    convert_oneof_to_anyof,
    ensure_type_in_schemas,
    fix_discriminator_mappings,
    force_additional_properties_false,
    resolve_refs,
    strip_null_from_types,
    strip_unsupported_formats,
)
from pydantic import BaseModel

LEAN_OBJECTS: frozenset[str] = frozenset({"LeadNote", "RiffNote", "PhrasePlan"})


def lean_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON schema exactly as CrewAI sends it, except that in the `LEAN_OBJECTS`
    `required` lists only the fields without a default — optional fields may be OMITTED instead
    of written out. Pure."""
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    schema = force_additional_properties_false(schema)
    schema = strip_unsupported_formats(schema)
    schema = ensure_type_in_schemas(schema)
    schema = resolve_refs(schema)
    schema.pop("$defs", None)
    schema = fix_discriminator_mappings(schema)
    schema = convert_oneof_to_anyof(schema)
    return _require_all_but_lean(_without_defaults(strip_null_from_types(schema)))


def _require_all_but_lean(node: Any) -> Any:
    """CrewAI's every-property-required rule, for every object NOT in `LEAN_OBJECTS`. Pure."""
    if isinstance(node, dict):
        node = {k: _require_all_but_lean(v) for k, v in node.items()}
        if (node.get("type") == "object" and node.get("properties")
                and node.get("title") not in LEAN_OBJECTS):
            node["required"] = list(node["properties"])
        return node
    if isinstance(node, list):
        return [_require_all_but_lean(v) for v in node]
    return node


def _without_defaults(node: Any) -> Any:
    """Drop every `default` — a stated default invites the model to write it out. Pure."""
    if isinstance(node, dict):
        return {k: _without_defaults(v) for k, v in node.items() if k != "default"}
    if isinstance(node, list):
        return [_without_defaults(v) for v in node]
    return node


def _top_level_ordering(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini's `propertyOrdering` on the top object only — the reasoning-first field order. Pure."""
    return {**schema, "propertyOrdering": list(schema.get("properties", {}))}


class LeanGemini(GeminiCompletion):
    """`GeminiCompletion` whose structured-output schema is `lean_schema` — the one change."""

    def _prepare_generation_config(self, system_instruction: str | None = None,
                                   tools: list[dict[str, Any]] | None = None,
                                   response_model: type[BaseModel] | None = None) -> Any:
        config = super()._prepare_generation_config(system_instruction, tools, response_model)
        if response_model is not None and getattr(config, "response_json_schema", None):
            config.response_json_schema = _top_level_ordering(lean_schema(response_model))
        return config
