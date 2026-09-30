"""Administrative commands. Run from ``backend/`` with the service key in .env.

    python -m agenlate.manage invites create --count 20 --label casa212
    python -m agenlate.manage invites list
    python -m agenlate.manage invites list --unused

Kept apart from ``agenlate.cli``, which runs roundtables: those need a user's
OpenRouter key, these need the service-role key, and a single entry point
that wanted both would make it too easy to run one with the other's
credentials to hand.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import invites
from .config import get_settings
from .db import create_service_client
from .repository import invites as invites_repo

MAX_BATCH = 200


async def _create(count: int, label: str | None) -> int:
    if not 1 <= count <= MAX_BATCH:
        print(f"--count must be between 1 and {MAX_BATCH}", file=sys.stderr)
        return 2

    # A set, because two identical draws out of 10^18 are not going to happen
    # — but if they did, the insert would fail on the primary key and take the
    # whole batch with it.
    codes: set[str] = set()
    while len(codes) < count:
        codes.add(invites.generate())

    client = await create_service_client(get_settings())
    try:
        created = await invites_repo.create_codes(client, sorted(codes), label)
    finally:
        await client.postgrest.aclose()

    print(f"Created {len(created)} code(s){f' labelled {label!r}' if label else ''}:\n")
    for code in created:
        print(f"  {code.code}")
    return 0


async def _list(unused_only: bool) -> int:
    client = await create_service_client(get_settings())
    try:
        codes = await invites_repo.list_codes(client)
    finally:
        await client.postgrest.aclose()

    shown = [c for c in codes if not (unused_only and c.is_claimed)]
    used = sum(1 for c in codes if c.is_claimed)
    print(f"{len(codes)} code(s): {used} used, {len(codes) - used} unused\n")
    for c in shown:
        state = f"used {c.claimed_at:%Y-%m-%d}" if c.is_claimed else "unused"
        print(f"  {c.code}  {state:<16} {c.label or ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agenlate.manage")
    area = parser.add_subparsers(dest="area", required=True)

    inv = area.add_parser("invites", help="Beta invite codes")
    action = inv.add_subparsers(dest="action", required=True)

    create = action.add_parser("create", help="issue new codes")
    create.add_argument("--count", type=int, default=1)
    create.add_argument("--label", help="where these are being handed out, e.g. casa212")

    listing = action.add_parser("list", help="show codes and whether each is used")
    listing.add_argument("--unused", action="store_true", help="only codes still available")

    args = parser.parse_args(argv)
    if args.action == "create":
        return asyncio.run(_create(args.count, args.label))
    return asyncio.run(_list(args.unused))


if __name__ == "__main__":
    raise SystemExit(main())
