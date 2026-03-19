"""Keypair GraphQL types package."""

from .filters import KeyPairFilterGQL, KeyPairOrderByGQL, KeyPairOrderFieldGQL
from .inputs import RevokeMyKeypairInputGQL, SwitchMyMainAccessKeyInputGQL, UpdateMyKeypairInputGQL
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
    "RevokeMyKeypairInputGQL",
    "SwitchMyMainAccessKeyInputGQL",
    "UpdateMyKeypairInputGQL",
    "IssueMyKeypairPayloadGQL",
    "RevokeMyKeypairPayloadGQL",
    "SwitchMyMainAccessKeyPayloadGQL",
    "UpdateMyKeypairPayloadGQL",
]
