import argparse
import asyncio
import logging
import uuid
from urllib.parse import parse_qs, urlparse

import msgspec
from websockets import WebSocketServerProtocol
from websockets.server import serve

from cs404x.arena import Arena, Participant
from cs404x.messages import Message

arena = Arena()

_USERNAME_QUERY = "username"


def _parse_username(uri: str):
    parsed_uri = urlparse(uri)
    uri_query = parse_qs(parsed_uri.query)

    if _USERNAME_QUERY not in uri_query:
        return None

    username, *_ = uri_query[_USERNAME_QUERY]

    return username


async def _arena_entry(websocket: WebSocketServerProtocol, uri: str):
    username = _parse_username(uri)

    if not username:
        await websocket.close(code=1006)
        return

    participant = Participant(
        user_name=username,
        user_id=str(uuid.uuid4()),
        websocket=websocket,
    )

    await arena.register(participant)

    try:
        async for message in websocket:
            message = msgspec.msgpack.decode(message, type=Message)
            await arena.on_message(participant, message)
    finally:
        await arena.deregister(participant)


async def _server(*, address: str, port: int):
    async with serve(_arena_entry, address, port):
        await asyncio.Future()


async def _launch_arena(*, address: str, port: int):
    await asyncio.gather(
        _server(address=address, port=port),
        arena.game_loop(),
    )


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--address",
        help="Address to listen on.",
        type=str,
        default="127.0.0.1",
        required=True,
    )
    parser.add_argument(
        "--port",
        help="The server port.",
        type=int,
        default=4040,
        required=True,
    )

    args = parser.parse_args()

    asyncio.run(
        _launch_arena(
            address=args.address,
            port=args.port,
        )
    )
