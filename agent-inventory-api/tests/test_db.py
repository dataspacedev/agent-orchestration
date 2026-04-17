from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_db_connection(db: AsyncSession) -> None:
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_agents_table_exists(db: AsyncSession) -> None:
    result = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    tables = {row[0] for row in result.fetchall()}
    assert "agents" in tables
