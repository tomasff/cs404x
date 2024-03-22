# cs404x
cs404x is a remote arena for agents of the CS404 Agent Based System module
at the University of Warwick. It includes a client and a server, and aims
for full compatibility with the "local" bots.

It is by no means production-ready, there are things that could definitely be
improved, but it was setup so that students can quickly test different
strategies against each other without having to share code, avoiding plagiarism
concerns.

## Installation

```sh
# (Recommended) with pipx
pipx install git+https://github.com/tomasff/cs404x.git

# With pip
pip install --user git+https://github.com/tomasff/cs404x.git
```

## Setup an arena
Arenas act as a single remote auction over websockets, and can be setup as
follows,
```sh
cs404x-server --address 0.0.0.0 --port 4040
```

## Connect to an arena
You'll need a bot as specified in the coursework specification,
```python
class Bot:
    def __init__(self):
        self.name = "flat_bot_10"

    def get_bid(
        self,
        current_round,
        bots,
        winner_pays,
        artists_and_values,
        round_limit,
        starting_budget,
        painting_order,
        target_collection,
        my_bot_details,
        current_painting,
        winner_ids,
        amounts_paid,
    ):
        return 10
```

You can then connect to an arena,
```sh
cs404x-client --username your_display_name \
    --address 127.0.0.1 \
    --port 4040 \
    --bot path/to/your/bot.py \
    --telemetry-base telemetry/ \
    --num-auctions 20
```

## Acknowledgements
The Auctioneer code takes inspiration from the Auctioneer provided in the CS404
module:

>The (original) code was developed by Charlie Pilgrim, Department of Mathematics,
>University of Warwick. A previous version of the coursework, from which this
>takes inspiration, was written by Alexander Carver, Department of Computing,
>Imperial College London. Further precious input for the coursework came from
>Charlotte Roman, Department of Mathematics, University of Warwick.

This software is inspired by another remote arena, [Cerutti](https://github.com/alexander-jackson/cerutti).
