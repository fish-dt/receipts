"""Per-job event log with optimistic locking and a hash chain (tamper-evident ordering)."""
from __future__ import annotations

import threading
import time
from typing import Any, Protocol

from .models import canonical, sha256_text

GENESIS = "0" * 64


class ConflictError(Exception):
    """The version the caller read is stale, or the job already exists."""


def chain_hash(prev: str, event: dict[str, Any]) -> str:
    return sha256_text(prev + canonical(event))


def verify_chain(events: list[dict[str, Any]]) -> bool:
    prev = GENESIS
    for ev in events:
        body = {k: v for k, v in ev.items() if k != "hash"}
        prev = chain_hash(prev, body)
        if ev.get("hash") != prev:
            return False
    return True


class ReceiptStore(Protocol):
    def create(self, job_id: str) -> int: ...
    def append(self, job_id: str, event: dict[str, Any], expected_version: int) -> int: ...
    def get(self, job_id: str) -> dict[str, Any]: ...


class MemoryStore:
    """Thread-safe in-memory store for tests and the offline demo."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str) -> int:
        with self._lock:
            if job_id in self._items:
                raise ConflictError("job already exists")
            self._items[job_id] = {"job_id": job_id, "version": 1, "events": [], "head": GENESIS}
            return 1

    def append(self, job_id: str, event: dict[str, Any], expected_version: int) -> int:
        with self._lock:
            item = self._items[job_id]
            if item["version"] != expected_version:
                raise ConflictError(f"stale version {expected_version}, current {item['version']}")
            item["head"] = chain_hash(item["head"], event)
            item["events"].append({**event, "hash": item["head"]})
            item["version"] += 1
            return item["version"]

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return {**self._items[job_id], "events": list(self._items[job_id]["events"])}


class DynamoStore:
    """DynamoDB-backed store. Items stay small (a handful of events) and expire via TTL."""

    def __init__(self, table_name: str, region: str | None = None, ttl_s: int = 7 * 86400) -> None:
        import boto3
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._ttl = ttl_s

    def create(self, job_id: str) -> int:
        from botocore.exceptions import ClientError
        try:
            self._table.put_item(
                Item={"job_id": job_id, "version": 1, "events": [], "head": GENESIS,
                      "expires_at": int(time.time()) + self._ttl},
                ConditionExpression="attribute_not_exists(job_id)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConflictError("job already exists") from exc
            raise
        return 1

    def append(self, job_id: str, event: dict[str, Any], expected_version: int) -> int:
        from botocore.exceptions import ClientError
        head = chain_hash(self.get(job_id)["head"], event)
        try:
            self._table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET events = list_append(events, :e), head = :h, version = :n",
                ConditionExpression="version = :v AND head = :prev",
                ExpressionAttributeValues={":e": [{**event, "hash": head}], ":h": head,
                                           ":n": expected_version + 1, ":v": expected_version,
                                           ":prev": self.get(job_id)["head"]})
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConflictError("stale version") from exc
            raise
        return expected_version + 1

    def get(self, job_id: str) -> dict[str, Any]:
        return self._table.get_item(Key={"job_id": job_id}, ConsistentRead=True)["Item"]
