"""Small generic data-access helper. It never commits."""

from typing import Any, Optional, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, model: type[T], id: Any) -> Optional[T]:
        return await self.session.get(model, id)

    async def get_all(
        self,
        model: type[T],
        *,
        order_by: Any = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[T]:
        stmt = select(model)
        if order_by is not None:
            if isinstance(order_by, (list, tuple)):
                stmt = stmt.order_by(*order_by)
            else:
                stmt = stmt.order_by(order_by)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).scalars()
        return [*rows]

    async def create(self, obj: T) -> T:
        """Stage ``obj``, flush so DB defaults are assigned, then reload it."""
        session = self.session
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def update_fields(self, model: type[T], id: Any, **fields: Any) -> Optional[T]:
        """Apply ``fields`` to the row with primary key ``id``; None when absent."""
        key_column = getattr(model, "id")
        stmt = update(model).values(**fields).where(key_column == id)
        stmt = stmt.returning(model).execution_options(synchronize_session="fetch")
        updated = (await self.session.execute(stmt)).scalars().first()
        if updated is not None:
            await self.session.flush()
        return updated

    async def delete_by_id(self, model: type[T], id: Any) -> bool:
        result = await self.session.execute(delete(model).where(model.id == id))  # type: ignore[attr-defined]
        return (result.rowcount or 0) > 0

    async def count(self, model: type[T]) -> int:
        result = await self.session.execute(select(func.count()).select_from(model))
        return int(result.scalar() or 0)
