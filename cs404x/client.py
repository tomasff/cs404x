import argparse
import asyncio
import csv
import logging
import uuid
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import quote_plus

import msgspec
from websockets import connect

from cs404x.messages import Message, MessageKind


def save_auction_telemetry(path: Path, telemetry: list[dict[Any, Any]]):
    with open(path, "w", encoding="utf8") as file:
        csv_writer = csv.DictWriter(
            file,
            fieldnames=[
                "auction_start",
                "current_round",
                "round_winner",
                "painting",
                "amount_paid",
            ],
        )

        csv_writer.writeheader()
        csv_writer.writerows(telemetry)


async def client(
    *,
    address: str,
    port: int,
    username: str,
    bot_cls: type,
    telemetry_base: Path,
):
    arena_uri = f"ws://{address}:{port}/?username={quote_plus(username)}"

    bot = None
    auctions_won = 0
    current_auction_telemetry = []

    async with connect(arena_uri) as websocket:
        async for message in websocket:
            message: Message = msgspec.msgpack.decode(message, type=Message)

            if message.kind == MessageKind.INFO:
                logging.info(message.value)
            elif message.kind == MessageKind.QUEUED:
                logging.info("Waiting in the queue: %s", message.value)
            elif message.kind == MessageKind.START:
                logging.info("Auction starting...")
                bot = bot_cls()
            elif message.kind == MessageKind.END:
                logging.info("Auction ended...")

                save_auction_telemetry(
                    telemetry_base / f"{uuid.uuid4()}.csv",
                    current_auction_telemetry,
                )

                current_auction_telemetry.clear()
            elif message.kind == MessageKind.WIN:
                auctions_won += 1

                logging.info(
                    "You won the auction (%d auctions won so far) (%d total players in auction).",
                    auctions_won,
                    message.value,
                )
            elif message.kind == MessageKind.ROUND_TELEMETRY:
                logging.info(
                    "Received auction round telemetry: %s.",
                    message.value,
                )
                current_auction_telemetry.append(message.value)
            elif message.kind == MessageKind.BID_REQUEST:
                logging.info("Received bid request.")

                bid = bot.get_bid(**message.value)

                logging.info("Bidding %f", bid)

                await websocket.send(
                    msgspec.msgpack.encode(
                        Message(MessageKind.BID_REPLY, value=bid)
                    )
                )


def _load_bot_module(path: Path) -> ModuleType:
    module_spec = spec_from_file_location("target_bot", path)
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    return module


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--username",
        help="Your display name.",
        type=str,
        required=True,
    )
    parser.add_argument(
        "--address",
        help="Arena server address.",
        type=str,
        default="127.0.0.1",
        required=True,
    )
    parser.add_argument(
        "--port",
        help="Arena server port.",
        type=int,
        default=80,
    )
    parser.add_argument(
        "--bot",
        help="Path to your bot (e.g. u00000.py)",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--telemetry-base",
        help="Directory where telemetry for each auction is to be stored.",
        type=Path,
        default="telemetry",
    )

    args = parser.parse_args()

    bot_module = _load_bot_module(args.bot)

    args.telemetry_base.mkdir(exist_ok=True)

    asyncio.run(
        client(
            username=args.username,
            bot_cls=bot_module.Bot,
            address=args.address,
            port=args.port,
            telemetry_base=args.telemetry_base,
        )
    )
