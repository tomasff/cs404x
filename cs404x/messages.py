from enum import IntEnum, auto
from typing import Any, Optional

import msgspec


class MessageKind(IntEnum):
    QUEUED = auto()
    START = auto()
    END = auto()
    WIN = auto()

    INFO = auto()
    WARNING = auto()

    ROUND_TELEMETRY = auto()

    BID_REPLY = auto()
    BID_REQUEST = auto()


class Message(msgspec.Struct):
    kind: MessageKind
    value: Optional[Any] = None
