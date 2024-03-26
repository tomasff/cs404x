import asyncio
import dataclasses
import logging
from typing import Iterable

import msgspec
from websockets import ConnectionClosed, WebSocketServerProtocol, broadcast

from cs404x.auctioneer import Auctioneer
from cs404x.messages import Message, MessageKind

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Participant:
    user_name: str
    user_id: str
    websocket: WebSocketServerProtocol

    def __hash__(self):
        return hash((self.user_name, self.user_id))


async def broadcast_message(
    participants: Iterable[Participant],
    message: Message,
):
    return broadcast(
        websockets=(participant.websocket for participant in participants),
        message=msgspec.msgpack.encode(message),
    )


class Arena:
    _MIN_PLAYERS = 2
    _TIMEOUT_START = 0
    _BID_TIMEOUT = 10

    def __init__(self):
        self._registration_lock = asyncio.Lock()
        self._sufficient_players_event = asyncio.Event()

        self._bids_received = 0
        self._all_bids_received_event = asyncio.Condition()

        self._participants_waiting = set()
        self._participants_in_game = {}

        self._auction = None

    @property
    def in_game(self) -> bool:
        return self._auction is not None

    async def deregister(self, participant: Participant):
        async with self._registration_lock:
            logger.info(
                "Participant %s (%s) left.",
                participant.user_name,
                participant.user_id,
            )
            self._participants_waiting.discard(participant)
            self._participants_in_game.pop(participant.user_id, None)

    async def register(self, participant: Participant):
        async with self._registration_lock:
            logger.info(
                "Participant %s (%s) joined.",
                participant.user_name,
                participant.user_id,
            )
            self._participants_waiting.add(participant)

            await self._send_message(
                participant,
                Message(
                    MessageKind.QUEUED,
                    value={
                        "is_in_game": self.in_game,
                        "participant_id": participant.user_id,
                        "in_game_count": len(self._participants_in_game),
                        "waiting_count": len(self._participants_waiting),
                    },
                ),
            )

        self._start_if_possible()

    def _start_if_possible(self):
        if (
            not self.in_game
            and len(self._participants_waiting) >= self._MIN_PLAYERS
        ):
            self._sufficient_players_event.set()
        else:
            self._sufficient_players_event.clear()

    async def game_loop(self):
        while True:
            logger.info("Waiting for players...")

            await self._sufficient_players_event.wait()

            logger.info(
                "Round starting with %d players...",
                len(self._participants_waiting),
            )

            await asyncio.sleep(self._TIMEOUT_START)

            await broadcast_message(
                self._participants_waiting,
                Message(MessageKind.START),
            )

            await self._setup_auction()

            while not self._auction.finished:
                if await self._run_round():
                    break

            await self._finish_auction()

    async def _run_round(self) -> bool:
        self._auction.start_round()

        await self._request_bids(self._participants_in_game.values())

        async with self._all_bids_received_event:
            try:
                await asyncio.wait_for(
                    self._all_bids_received_event.wait(),
                    self._BID_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logging.warning("Did not receive all bids...continuing")

        if len(self._participants_in_game) < self._MIN_PLAYERS:
            logging.info(
                "Cancelling auction, less than %d players present.",
                self._MIN_PLAYERS,
            )
            return True

        round_summary = self._auction.finish_round()

        await broadcast_message(
            self._participants_in_game.values(),
            message=Message(
                MessageKind.ROUND_TELEMETRY,
                value=round_summary,
            ),
        )

        return False

    async def _setup_auction(self):
        async with self._registration_lock:
            self._participants_in_game = {
                participant.user_id: participant
                for participant in self._participants_waiting
            }
            self._participants_waiting.clear()

            self._auction = Auctioneer(
                players=self._participants_in_game,
            )

    async def _finish_auction(self):
        winners = set(self._auction.compute_auction_winners())

        for participant_id, participant in self._participants_in_game.items():
            participant_message = {
                "won": participant_id in winners,
                "participants": len(self._participants_in_game),
            }

            asyncio.create_task(
                self._send_message(
                    participant,
                    Message(MessageKind.END, value=participant_message),
                )
            )

        async with self._registration_lock:
            self._auction = None

            self._participants_waiting.update(
                self._participants_in_game.values()
            )
            self._participants_in_game.clear()

            self._start_if_possible()

    async def _request_bids(self, participants: Iterable[Participant]):
        summary_auction_state = self._auction.summary_state
        all_participants_state = {
            participant: self._auction.get_participant_state(participant)
            for participant in self._participants_in_game.keys()
        }

        for participant in participants:
            participant_state = {
                **summary_auction_state,
                "my_bot_details": all_participants_state[participant.user_id],
                "bots": list(all_participants_state.values()),
            }

            asyncio.create_task(
                self._send_message(
                    participant,
                    Message(
                        kind=MessageKind.BID_REQUEST,
                        value=participant_state,
                    ),
                )
            )

    async def _send_message(self, participant: Participant, message: Message):
        try:
            await participant.websocket.send(msgspec.msgpack.encode(message))
        except ConnectionClosed:
            await self.deregister(participant)

    async def _on_bid_reply(self, participant: Participant, message: Message):
        if participant in self._participants_waiting:
            await self._send_message(
                participant,
                Message(
                    MessageKind.WARNING, value="Can't bid while in queue."
                ),
            )
            return

        within_budget = self._auction.register_bid(
            player_id=participant.user_id,
            bid=message.value,
        )

        if not within_budget:
            await self._send_message(
                participant,
                Message(
                    MessageKind.WARNING,
                    value="Bid exceeds budget available.",
                ),
            )
        else:
            await self._count_bids()

    async def _count_bids(self):
        async with self._all_bids_received_event, self._registration_lock:
            self._bids_received += 1

            if self._bids_received == len(self._participants_in_game):
                self._bids_received = 0
                self._all_bids_received_event.notify_all()

    async def on_message(
        self,
        participant: Participant,
        message: Message,
    ):
        if message.kind == MessageKind.BID_REPLY:
            await self._on_bid_reply(participant, message)
