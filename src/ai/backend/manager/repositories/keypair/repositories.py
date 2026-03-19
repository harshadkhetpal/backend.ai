from dataclasses import dataclass
from typing import Self

from ai.backend.manager.repositories.keypair.repository import KeyPairRepository
from ai.backend.manager.repositories.types import RepositoryArgs


@dataclass
class KeyPairRepositories:
    repository: KeyPairRepository

    @classmethod
    def create(cls, args: RepositoryArgs) -> Self:
        repository = KeyPairRepository(args.db)

        return cls(
            repository=repository,
        )
