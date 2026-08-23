"""Validate migration e5b2c8f41a90 in isolation against SQLite.

The full alembic chain can't run on SQLite (old PG-only FK migration
b7f2c1a94d03), so we reconstruct the pre-migration schema via metadata,
stamp the predecessor revision, and apply only this revision.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("TEMP", "/tmp"), "opencode", "mig-iso.db"
)
os.environ["CVX_DATABASE_URL"] = "sqlite+aiosqlite:///" + DB.replace("\\", "/")

API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg() -> "Config":  # noqa: F821
    from alembic.config import Config

    return Config(os.path.join(API_ROOT, "alembic.ini"))


async def _build_pre_migration_schema() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.base import Base
    import app.models  # noqa: F401  # register all models

    if os.path.exists(DB):
        os.remove(DB)
    engine = create_async_engine(os.environ["CVX_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Rewind to the pre-migration state.
        await conn.execute(text("DROP TABLE provisioning_jobs"))
        await conn.execute(text("ALTER TABLE vps DROP COLUMN root_password_encrypted"))
    await engine.dispose()


async def _verify_upgrade() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["CVX_DATABASE_URL"])
    async with engine.begin() as conn:
        cols = await conn.execute(text("SELECT name FROM pragma_table_info('vps')"))
        assert "root_password_encrypted" in [r[0] for r in cols], "column missing"

        await conn.execute(text(
            "INSERT INTO provisioning_jobs (id, vps_id) "
            "VALUES ('018f0000-0000-7000-8000-000000000001', NULL)"
        ))
        row = (
            await conn.execute(text(
                "SELECT kind, status, stage, progress FROM provisioning_jobs"
            ))
        ).one()
        assert row == ("vps_create", "queued", "", 0), row
        try:
            await conn.execute(text(
                "INSERT INTO provisioning_jobs (id, status) "
                "VALUES ('018f0000-0000-7000-8000-000000000002', 'bogus')"
            ))
            raise SystemExit("check constraint NOT enforced")
        except SystemExit:
            raise
        except Exception:
            pass
        idx = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='provisioning_jobs'"
        ))
        names = {r[0] for r in idx}
        for expected in (
            "ix_provisioning_jobs_status", "ix_provisioning_jobs_vps_id",
            "ix_provisioning_jobs_user_id", "ix_jobs_status_created",
        ):
            assert expected in names, f"missing index {expected}: {names}"
    await engine.dispose()
    print("upgrade OK: column, defaults, check constraint, indexes all verified")


async def _verify_downgrade() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["CVX_DATABASE_URL"])
    async with engine.begin() as conn:
        jobs = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provisioning_jobs'"
        ))
        assert jobs.first() is None, "table still present after downgrade"
        cols = await conn.execute(text("SELECT name FROM pragma_table_info('vps')"))
        assert "root_password_encrypted" not in [r[0] for r in cols], "column survived"
    await engine.dispose()
    print("downgrade OK: table dropped, column removed")


def main() -> None:
    from alembic import command

    cfg = _cfg()
    asyncio.run(_build_pre_migration_schema())
    command.stamp(cfg, "c3a9d7e51b84")
    command.upgrade(cfg, "head")
    asyncio.run(_verify_upgrade())
    command.downgrade(cfg, "-1")
    asyncio.run(_verify_downgrade())
    if os.path.exists(DB):
        os.remove(DB)


if __name__ == "__main__":
    main()
