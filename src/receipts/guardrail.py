"""Bedrock Guardrail creation and screening of untrusted job text. Verify parameters against current docs."""
from __future__ import annotations

SECRET_TYPES = ("AWS_ACCESS_KEY", "AWS_SECRET_KEY", "PASSWORD")


def create_guardrail(name: str = "receipts-guardrail", region: str | None = None) -> tuple[str, str]:
    """Idempotently create the guardrail and publish an immutable version. Returns (id, version)."""
    import boto3
    client = boto3.client("bedrock", region_name=region)
    existing = next((g for g in client.list_guardrails().get("guardrails", []) if g["name"] == name), None)
    if existing:
        gid = existing["id"]
    else:
        gid = client.create_guardrail(
            name=name,
            blockedInputMessaging="Input blocked by policy.",
            blockedOutputsMessaging="Output blocked by policy.",
            contentPolicyConfig={"filtersConfig": [
                {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"}]},
            sensitiveInformationPolicyConfig={"piiEntitiesConfig": [
                {"type": t, "action": "BLOCK"} for t in SECRET_TYPES]},
        )["guardrailId"]
    return gid, client.create_guardrail_version(guardrailIdentifier=gid)["version"]


def make_screen(guardrail_id: str, version: str, region: str | None = None):
    """Return screen(text) -> bool (True = allowed). Marks the text as guarded content."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=region)

    def screen(text: str) -> bool:
        resp = client.apply_guardrail(
            guardrailIdentifier=guardrail_id, guardrailVersion=version, source="INPUT",
            content=[{"text": {"text": text, "qualifiers": ["guard_content"]}}])
        return resp["action"] != "GUARDRAIL_INTERVENED"

    return screen
