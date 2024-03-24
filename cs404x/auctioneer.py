"""Auctioneer for primarily paiting collection games.

Please note that this has been modified from the original Auctioneer
code provided for the CS404 module at the University of Warwick
to accomodate for the set-up of a remote arena.

Acknowledgments from the code this Auctioneer takes inspiration from:
The (original) code was developed by Charlie Pilgrim, Department of Mathematics,
University of Warwick. A previous version of the coursework, from which this
takes inspiration, was written by Alexander Carver, Department of Computing,
Imperial College London. Further precious input for the coursework came from
Charlotte Roman, Department of Mathematics, University of Warwick.
"""
import dataclasses
import datetime
import random
from collections.abc import Sequence
from typing import Any, Optional


class ParticipantState:
    def __init__(self, budget: float, paintings: Sequence[str]):
        self.paintings_owned = {painting: 0 for painting in paintings}

        self.budget = budget
        self.score = 0
        self.current_bid = None

    def to_dict(self):
        return {
            "paintings": self.paintings_owned,
            "budget": self.budget,
            "score": self.score,
        }


@dataclasses.dataclass
class RoundSummary:
    """Overall summary of an auction round.

    Attributes:
        auction_start: Time when the auction started.
        current_round: Current round number.
        round_winner: ID (unique) of the participant who won the round.
        painting: The painting which was acquired.
        amount_paid: How much was paid for `painting` (bid).
    """

    auction_start: datetime.datetime
    current_round: int
    round_winner: str
    painting: str
    amount_paid: float


class Auctioneer:
    def __init__(
        self,
        players: Sequence[str],
        painting_order: Optional[Sequence[int]] = None,
        target_collection: Sequence[int] = (
            3,
            3,
            1,
            1,
        ),
    ):
        self._player_won = False
        self._current_round = 0

        self._round_limit = 200
        self._starting_budget = 1001
        self._artists_and_values = {
            "Da Vinci": 7,
            "Rembrandt": 3,
            "Van Gogh": 12,
            "Picasso": 2,
        }
        self._target_collection = target_collection

        self._players = {
            player: ParticipantState(
                budget=self._starting_budget,
                paintings=self._artists_and_values.keys(),
            )
            for player in players
        }

        random.seed()

        self._painting_order = painting_order

        if self._painting_order is None:
            # Random painting order if none given
            artists = list(self._artists_and_values.keys())
            self._painting_order = [
                artists[random.randint(0, 3)] for _ in range(self._round_limit)
            ]

        # Winner pays 1nd price auction
        self._winner_pays = 1

        self._auction_start = datetime.datetime.now()
        self._winner_ids = []
        self._amounts_paid = []

    @property
    def finished(self) -> bool:
        return (
            self._current_round == self._round_limit - 1
        ) or self._player_won

    def start_round(self):
        for state in self._players.values():
            state.current_bid = 0

    @property
    def summary_state(self) -> dict[str, Any]:
        return {
            "current_round": self._current_round,
            "winner_pays": self._winner_pays,
            "artists_and_values": self._artists_and_values,
            "round_limit": self._round_limit,
            "starting_budget": self._starting_budget,
            "painting_order": self._painting_order,
            "target_collection": self._target_collection,
            "current_painting": self._painting_order[self._current_round],
            "winner_ids": self._winner_ids,
            "amounts_paid": self._amounts_paid,
        }

    def get_participant_state(self, user_id: str):
        return self._players[user_id].to_dict()

    def register_bid(self, player_id: str, bid: float) -> bool:
        if bid <= self._players[player_id].budget:
            self._players[player_id].current_bid = bid
            return True

        self._players[player_id].current_bid = 0
        return False

    def finish_round(self) -> RoundSummary:
        self._compute_round_winner()
        self._update_scores()

        round_summary = RoundSummary(
            auction_start=self._auction_start,
            current_round=self._current_round,
            round_winner=self._winner_ids[self._current_round],
            painting=self._painting_order[self._current_round],
            amount_paid=self._amounts_paid[self._current_round],
        )

        self._current_round += 1

        return round_summary

    def _compute_round_winner(self):
        # Sort the bots based on their current bid. If there is a tie, randomly break the tie
        sorted_players = sorted(
            self._players,
            key=lambda p: (self._players[p].current_bid, random.random()),
            reverse=True,
        )

        bid_position_to_pay = min(self._winner_pays, len(sorted_players)) - 1

        # Award the painting to the winning bot, the first in the sorted array of bots
        winner_id = sorted_players[bid_position_to_pay]
        winner_state = self._players[winner_id]

        # Subtract bid value from the winning bot's budget
        winner_state.budget -= winner_state.current_bid
        self._amounts_paid.append(winner_state.current_bid)

        # Add painting to winner's paintings
        current_painting = self._painting_order[self._current_round]
        winner_state.paintings_owned[current_painting] += 1
        self._winner_ids.append(winner_id)

    def _update_scores(self):
        """
        Works out the score for each bot based on painting values

        Checks to see if any bots have a full collection.
        Score is 1 for full collection and 0 otherwise
        """

        for player_state in self._players.values():
            player_state.score = 0

            # Sort this bot's painting counts, and target counts, with highest value first
            bot_painting_counts_sorted = sorted(
                player_state.paintings_owned.values(),
                reverse=True,
            )
            target_painting_counts_sorted = sorted(
                self._target_collection,
                reverse=True,
            )

            # Subtract target painting counts from this bot's painting count
            paintings_needed = [
                target - bot_painting_counts_sorted[index]
                for index, target in enumerate(target_painting_counts_sorted)
            ]
            # If all the paintings needed counts are 0 or less, then the collection is complete
            if max(paintings_needed) < 1:
                player_state.score = 1
                self._player_won = True

    def compute_auction_winners(self) -> list[str]:
        """
        Declare the winners, based on who has the maximum score.
        Returns a list of winners
        Collection game - the winner has score of 1 while losers have score of 0
        """
        if not self._players:
            return []

        winning_score = max(player.score for player in self._players.values())

        winners = [
            player
            for player, player_state in self._players.items()
            if player_state.score == winning_score
        ]

        return winners
