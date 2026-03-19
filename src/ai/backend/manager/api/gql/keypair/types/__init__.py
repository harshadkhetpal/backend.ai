"""Keypair GraphQL types package."""

from .filters import KeyPairFilterGQL, KeyPairOrderByGQL, KeyPairOrderFieldGQL
from .inputs import RevokeMyKeypairInputGQL, SwitchMyMainAccessKeyInputGQL, UpdateMyKeypairInputGQL
from .node import MyKeypairConnection, MyKeypairEdge, MyKeypairGQL
from .payloads import (
    IssueMyKeypairPayloadGQL,
    RevokeMyKeypairPayloadGQL,
    SwitchMyMainAccessKeyPayloadGQL,
    UpdateMyKeypairPayloadGQL,
)

__all__ = [
    "KeyPairFilterGQL",
    "KeyPairOrderByGQL",
    "KeyPairOrderFieldGQL",
    "MyKeypairConnection",
    "MyKeypairEdge",
    "MyKeypairGQL",
    "RevokeMyKeypairInputGQL",
    "SwitchMyMainAccessKeyInputGQL",
    "UpdateMyKeypairInputGQL",
    "IssueMyKeypairPayloadGQL",
    "RevokeMyKeypairPayloadGQL",
    "SwitchMyMainAccessKeyPayloadGQL",
    "UpdateMyKeypairPayloadGQL",
]
