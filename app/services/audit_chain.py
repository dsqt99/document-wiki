"""Tamper-evident audit chain for `audit_log`.

Every entry carries `event_hash = HMAC-SHA256(key, canonical JSON of the entry + prev_hash)` and a contiguous
`seq`; `audit_chain_head` holds a signed pointer to the last entry. Together they expose edited fields (hash),
deleted or inserted entries (seq gap / prev_hash), tail deletion and chain replacement (signed head).
Postgres triggers (migration 049) additionally reject UPDATE/DELETE/TRUNCATE on the log.

The HMAC key lives outside the database (AUDIT_HMAC_KEY). Whoever holds both database superuser rights and the
key can still rewrite history, so ship the `AUDIT_ANCHOR` log lines to a store the database admin cannot edit.
`record()` writes in its own short transaction so the chain lock is never held across a slow request.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import AuditChainHead, AuditLog
from app.services.trace_context import get_trace_id

log = logging.getLogger(__name__)
anchor_log = logging.getLogger("audit.chain")

CHAIN_VERSION = 2
GENESIS_HASH = "GENESIS_HASH_ARKON_WIKI_CHAIN_0000000000"
BASELINE_ACTION = "AUDIT_CHAIN_BASELINE"
NIL_UUID = uuid.UUID(int=0)
_CHAIN_LOCK = 7420501003
_warned_derived_key = False


def _chain_key() -> bytes:
    global _warned_derived_key
    configured = (settings.audit_hmac_key or "").strip()
    if configured:
        return configured.encode("utf-8")
    if not _warned_derived_key:
        log.warning("AUDIT_HMAC_KEY is not set: deriving the audit chain key from SECRET_KEY.")
        _warned_derived_key = True
    return hmac.new(settings.secret_key.encode("utf-8"), b"wiki-audit-chain-key-v1", hashlib.sha256).digest()


def _key_fingerprint(key: bytes) -> str:
    return hashlib.sha256(b"fingerprint:" + key).hexdigest()[:16]


def _json_safe(value: Any) -> dict:
    return json.loads(json.dumps(value if value is not None else {}, default=str, ensure_ascii=False))


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


_FIELDS = (
    "seq", "id", "trace_id", "principal_id", "principal_type", "action",
    "resource_type", "resource_id", "decision", "reason", "metadata_", "timestamp", "prev_hash",
)


def _hashable(row: Any) -> dict:
    """Exactly the fields covered by the HMAC, from an AuditLog row or a dict with the same attribute names."""
    values = {f: (row[f] if isinstance(row, dict) else getattr(row, f)) for f in _FIELDS}
    return {
        "v": CHAIN_VERSION,
        "seq": int(values["seq"]),
        "id": str(values["id"]),
        "trace_id": values["trace_id"],
        "principal_id": str(values["principal_id"]),
        "principal_type": values["principal_type"],
        "action": values["action"],
        "resource_type": values["resource_type"],
        "resource_id": values["resource_id"],
        "decision": values["decision"],
        "reason": values["reason"],
        "metadata": values["metadata_"],
        "timestamp": _iso(values["timestamp"]),
        "prev_hash": values["prev_hash"],
    }


def compute_event_hash(row: Any, key: bytes) -> str:
    return hmac.new(key, _canonical(_hashable(row)), hashlib.sha256).hexdigest()


def _head_signature(seq: int, event_hash: str, key: bytes) -> str:
    return hmac.new(key, f"head:{seq}:{event_hash}".encode("utf-8"), hashlib.sha256).hexdigest()


def current_trace_id() -> str:
    return (get_trace_id() or f"tr-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}")[:64]


async def _legacy_digest(session: AsyncSession) -> dict:
    """Fingerprint of the pre-chain rows archived in audit_log_legacy (SHA-256 over every column)."""
    exists = (await session.execute(text("SELECT to_regclass('audit_log_legacy')"))).scalar()
    if not exists:
        return {"legacy_rows": 0, "legacy_digest": hashlib.sha256(b"").hexdigest()}
    rows = (await session.execute(text("SELECT * FROM audit_log_legacy ORDER BY timestamp, id"))).mappings().all()
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(dict(row), sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\n")
    return {"legacy_rows": len(rows), "legacy_digest": digest.hexdigest()}


async def _insert(
    session: AsyncSession,
    key: bytes,
    fields: dict,
    *,
    trusted: bool,
    last_seq: int,
    last_hash: str,
    head: Optional[AuditChainHead],
) -> tuple[AuditLog, Optional[AuditChainHead]]:
    now = datetime.now(timezone.utc)
    record = {
        "id": uuid.uuid4(),
        "seq": last_seq + 1,
        "trace_id": current_trace_id(),
        "timestamp": now,
        "prev_hash": last_hash,
        **fields,
    }
    entry = AuditLog(**record)
    entry.event_hash = compute_event_hash(record, key)
    session.add(entry)
    if trusted:
        if head is None:
            head = AuditChainHead(id=1)
            session.add(head)
        head.last_seq = entry.seq
        head.last_hash = entry.event_hash
        head.key_fingerprint = _key_fingerprint(key)
        head.signature = _head_signature(entry.seq, entry.event_hash, key)
        head.updated_at = now
    await session.flush()
    session.info.setdefault("audit_anchors", []).append((entry.seq, entry.event_hash))
    return entry, head


async def append_entry(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    decision: str = "allow",
    reason: Optional[str] = None,
    principal_type: str = "human",
    metadata: Optional[dict] = None,
) -> AuditLog:
    """Append one entry inside `session`'s transaction (caller commits). Serialised by a transaction advisory lock."""
    key = _chain_key()
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK})

    head = (await session.execute(select(AuditChainHead).where(AuditChainHead.id == 1))).scalar_one_or_none()
    tail = (
        await session.execute(select(AuditLog.seq, AuditLog.event_hash).order_by(AuditLog.seq.desc()).limit(1))
    ).first()
    payload = _json_safe(metadata)

    if tail is None:
        baseline_meta = {"chain_version": CHAIN_VERSION, "algorithm": "HMAC-SHA256", **await _legacy_digest(session)}
        trusted = head is None
        if not trusted:
            baseline_meta["_chain_alert"] = "head_without_entries"
        baseline = {
            "principal_id": NIL_UUID, "principal_type": "system", "action": BASELINE_ACTION,
            "resource_type": "audit", "resource_id": "audit_log", "decision": "allow", "reason": None,
            "metadata_": baseline_meta,
        }
        first, head = await _insert(session, key, baseline, trusted=trusted, last_seq=0, last_hash=GENESIS_HASH, head=head)
        last_seq, last_hash = first.seq, first.event_hash
    else:
        last_seq, last_hash = int(tail[0]), tail[1]
        trusted = (
            head is not None
            and head.last_seq == last_seq
            and head.last_hash == last_hash
            and hmac.compare_digest(head.signature, _head_signature(head.last_seq, head.last_hash, key))
        )

    if not trusted:
        # Never "repair" the head: leave it so verification keeps failing until someone investigates.
        payload["_chain_alert"] = "head_mismatch_or_missing"
        log.critical("Audit chain does not match its signed head; appending anyway, investigation required.")

    entry, _ = await _insert(
        session, key,
        {
            "principal_id": principal_id, "principal_type": principal_type, "action": action[:50],
            "resource_type": resource_type[:50], "resource_id": str(resource_id)[:100],
            "decision": (decision or "allow")[:10], "reason": reason, "metadata_": payload,
        },
        trusted=trusted, last_seq=last_seq, last_hash=last_hash, head=head,
    )
    return entry


async def record(**kwargs: Any) -> AuditLog:
    """Append in a dedicated short transaction, so the chain lock is held for milliseconds, never across a request."""
    from app.database import async_session_factory

    async with async_session_factory() as session:
        try:
            entry = await append_entry(session, **kwargs)
            await session.commit()
            return entry
        except Exception:
            await session.rollback()
            raise


@event.listens_for(Session, "after_commit")
def _emit_anchors(session: Session) -> None:
    # External anchor: log shippers keep these lines outside the database, so a replaced database is detectable.
    for seq, event_hash in session.info.pop("audit_anchors", []):
        anchor_log.info("AUDIT_ANCHOR seq=%s hash=%s", seq, event_hash)


@event.listens_for(Session, "after_rollback")
def _drop_anchors(session: Session) -> None:
    session.info.pop("audit_anchors", None)


async def verify_chain(session: AsyncSession, batch_size: int = 2000) -> dict:
    """Check seq continuity, prev_hash links, every HMAC, the signed head and the legacy archive fingerprint."""
    key = _chain_key()
    verified_at = datetime.now(timezone.utc).isoformat()
    total, expected_seq, prev_hash, baseline = 0, 1, GENESIS_HASH, None

    def broken(row_id: Optional[str], seq: Optional[int], message: str) -> dict:
        return {"valid": False, "broken_at_event_id": row_id, "broken_at_seq": seq, "total_events": total,
                "verified_at": verified_at, "algorithm": "HMAC-SHA256", "message": message}

    cursor = 0
    while True:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.seq > cursor).order_by(AuditLog.seq.asc()).limit(batch_size)
            )
        ).scalars().all()
        if not rows:
            break
        for r in rows:
            if r.seq != expected_seq:
                return broken(str(r.id), r.seq, f"Sequence gap: expected {expected_seq}, found {r.seq}; entries were deleted or inserted.")
            if r.prev_hash != prev_hash:
                return broken(str(r.id), r.seq, f"Entry {r.id} does not link to its predecessor; the chain was forked or replaced.")
            if not hmac.compare_digest(compute_event_hash(r, key), r.event_hash or ""):
                return broken(str(r.id), r.seq, f"HMAC of entry {r.id} does not match its content; the entry was modified.")
            if r.seq == 1 and r.action == BASELINE_ACTION:
                baseline = r.metadata_ or {}
            prev_hash, expected_seq, total = r.event_hash, expected_seq + 1, total + 1
        cursor = rows[-1].seq

    head = (await session.execute(select(AuditChainHead).where(AuditChainHead.id == 1))).scalar_one_or_none()
    legacy = await _legacy_digest(session)
    last_seq = expected_seq - 1

    if total == 0 and head is None:
        return {"valid": True, "total_events": 0, "verified_at": verified_at, "algorithm": "HMAC-SHA256",
                "message": "No audit entries to verify yet."}
    if head is None:
        return broken(None, last_seq, "Signed chain head is missing; the chain may have been deleted or replaced.")
    if head.key_fingerprint != _key_fingerprint(key):
        return broken(None, last_seq, "The current HMAC key differs from the one that signed the chain (AUDIT_HMAC_KEY changed or lost).")
    if not hmac.compare_digest(head.signature or "", _head_signature(head.last_seq, head.last_hash, key)):
        return broken(None, last_seq, "Signature of the chain head is invalid; the head was modified.")
    if head.last_seq != last_seq or head.last_hash != prev_hash:
        return broken(None, last_seq, f"Last entry ({last_seq}) does not match the signed head ({head.last_seq}); the tail was deleted.")
    if baseline is not None and (
        baseline.get("legacy_rows") != legacy["legacy_rows"] or baseline.get("legacy_digest") != legacy["legacy_digest"]
    ):
        return broken(None, 1, "The archived pre-chain log no longer matches the fingerprint recorded in the baseline.")

    return {
        "valid": True, "total_events": total, "verified_at": verified_at, "algorithm": "HMAC-SHA256",
        "chain_version": CHAIN_VERSION, "head_seq": head.last_seq, "head_hash": head.last_hash,
        "legacy_rows": legacy["legacy_rows"],
        "message": f"All {total} entries match the HMAC chain and the signed head; no tampering detected.",
    }
