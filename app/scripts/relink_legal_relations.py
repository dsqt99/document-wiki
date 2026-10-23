"""Bounded legal-graph repair; defaults to a nonmutating preview.

    python -m app.scripts.relink_legal_relations --limit 100
    python -m app.scripts.relink_legal_relations --limit 100 --apply

Use the returned next_after_id with --after-id to scan subsequent batches.
Restart without a cursor to revisit unresolved targets after new ingestion.
The command only creates missing document roots and links unresolved edges;
it never regenerates source text, Wiki pages, or relations.
"""
import argparse
import asyncio
import json
import uuid


def _bounded_limit(value):
    value = int(value)
    if not 1 <= value <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return value


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=_bounded_limit, default=100)
    p.add_argument("--after-id", type=uuid.UUID)
    p.add_argument("--source-id", type=uuid.UUID)
    p.add_argument("--apply", action="store_true", help="Apply this one batch (default: dry-run)")
    return p


async def run(args):
    from app.database import async_session_factory
    from app.services.legal_relation_extractor import relink_legal_relations

    async with async_session_factory() as session:
        try:
            result = await relink_legal_relations(
                session, source_id=args.source_id, limit=args.limit,
                after_id=args.after_id, dry_run=not args.apply)
            if args.apply:
                await session.commit()
            else:
                await session.rollback()
        except BaseException:
            await session.rollback()
            raise
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run(parser().parse_args()))
