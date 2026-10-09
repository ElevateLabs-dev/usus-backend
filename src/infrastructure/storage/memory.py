import uuid
from typing import Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class MemoryRepository(Generic[T]):
    """
    In-memory storage for rapid prototyping and CLI testing before
    full PostgreSQL repositories are implemented.
    """

    def __init__(self):
        # Maps storage by tenant_id -> entity_id -> T
        self._storage: Dict[uuid.UUID, Dict[uuid.UUID, T]] = {}

    def save(self, tenant_id: uuid.UUID, entity: T) -> T:
        if tenant_id not in self._storage:
            self._storage[tenant_id] = {}

        # Assuming the entity has an 'id' attribute
        entity_id = getattr(entity, "id", None)
        if not entity_id:
            raise ValueError("Entity must have an 'id' attribute to be saved.")

        self._storage[tenant_id][entity_id] = entity
        return entity

    def get(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Optional[T]:
        if tenant_id in self._storage:
            return self._storage[tenant_id].get(entity_id)
        return None

    def list_all(self, tenant_id: uuid.UUID) -> List[T]:
        if tenant_id in self._storage:
            return list(self._storage[tenant_id].values())
        return []

    def delete(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> bool:
        if tenant_id in self._storage and entity_id in self._storage[tenant_id]:
            del self._storage[tenant_id][entity_id]
            return True
        return False
