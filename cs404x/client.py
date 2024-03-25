import argparse
import asyncio
import csv
import dataclasses
import logging
import uuid
from collections.abc import Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Awaitable, Optional
from urllib.parse import quote_plus

import msgspec
from websockets import WebSocketClientProtocol, connect

from cs404x.messages import Message, MessageKind


def save_auction_telemetry(path: Path, telemetry: list[dict[Any, Any]]):
    with open(path, "w", encoding="utf8") as file:
        csv_writer = csv.DictWriter(
            file,
            fieldnames=[
                "auction_start",
                "current_round",
                "round_winner_is_you",
                "round_winner",
                "painting",
                "amount_paid",
            ],
        )

        csv_writer.writeheader()
        csv_writer.writerows(telemetry)


@dataclasses.dataclass
class ClientState:
    bot: Any
    bot_cls: type
    telemetry_base: Path
    participant_id: Optional[str] = None
    auctions_won: int = 0
    auctions_total: int = 0
    current_auction_telemetry: list[Any] = dataclasses.field(
        default_factory=list,
    )


async def _on_info(
    _: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.info(message.value)
    return state


async def _on_warning(
    _: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.warning(message.value)
    return state


async def _on_queued(
    _: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.info("Waiting in the queue: %s", message.value)
    return dataclasses.replace(
        state, participant_id=message.value["participant_id"],
    )


async def _on_start(
    websocket: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.info("Auction starting...")
    return dataclasses.replace(state, bot=state.bot_cls())


async def _on_end(
    websocket: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.info("Auction ended: %s", message.value)

    save_auction_telemetry(
        (state.telemetry_base / str(uuid.uuid4())).with_suffix(".csv"),
        state.current_auction_telemetry,
    )

    if message.value["participants"] == 1:
        logging.info(
            "Auction terminatted early (only 1 participant): ignored."
        )

        return dataclasses.replace(
            state,
            current_auction_telemetry=[],
        )
    else:
        auctions_won = (
            state.auctions_won + 1
            if message.value["won"]
            else state.auctions_won
        )

        return dataclasses.replace(
            state,
            auctions_total=state.auctions_total + 1,
            auctions_won=auctions_won,
            current_auction_telemetry=[],
        )


async def _on_telemetry(
    websocket: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.debug(
        "Received auction round telemetry: %s.",
        message.value,
    )

    round_winner_is_you = state.participant_id == message.value["round_winner"]

    if state.participant_id is None:
        logging.warning(
            "Your participant ID is unknown, the provided auction logs may be inaccurate."
        )

    state.current_auction_telemetry.append(
        {
            **message.value,
            "round_winner_is_you": round_winner_is_you,
        }
    )

    return state


async def _on_bid_request(
    websocket: WebSocketClientProtocol,
    state: ClientState,
    message: Message,
) -> ClientState:
    logging.debug("Received bid request.")

    bid = state.bot.get_bid(**message.value)

    logging.debug("Bidding %f", bid)

    await websocket.send(
        msgspec.msgpack.encode(Message(MessageKind.BID_REPLY, value=bid))
    )

    return state


EventHandler = Callable[
    [WebSocketClientProtocol, ClientState, Message], Awaitable[ClientState]
]


async def client(
    *,
    address: str,
    port: int,
    username: str,
    bot_cls: type,
    telemetry_base: Path,
    num_auctions: int,
):
    arena_uri = f"ws://{address}:{port}/?username={quote_plus(username)}"

    state = ClientState(
        bot=None,
        bot_cls=bot_cls,
        telemetry_base=telemetry_base,
    )

    async with connect(arena_uri) as websocket:
        async for message in websocket:
            message: Message = msgspec.msgpack.decode(message, type=Message)

            on_event_handler: dict[MessageKind, EventHandler] = {
                MessageKind.INFO: _on_info,
                MessageKind.WARNING: _on_warning,
                MessageKind.QUEUED: _on_queued,
                MessageKind.START: _on_start,
                MessageKind.END: _on_end,
                MessageKind.ROUND_TELEMETRY: _on_telemetry,
                MessageKind.BID_REQUEST: _on_bid_request,
            }

            state = await on_event_handler[message.kind](
                websocket,
                state,
                message,
            )

            if state.auctions_total == num_auctions:
                break

    logging.info(
        "Finished, win rate: %f, total auctions %d, auctions won %d",
        state.auctions_won / state.auctions_total,
        state.auctions_total,
        state.auctions_won,
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
        "--num-auctions",
        help="Number of auctions you want to take part in.",
        type=int,
        default=50,
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
            num_auctions=args.num_auctions,
            telemetry_base=args.telemetry_base,
        )
    )
