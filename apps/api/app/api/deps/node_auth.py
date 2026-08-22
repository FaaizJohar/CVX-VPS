from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.models import Node
from app.services.node_service import NodeService

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_node(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Node:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Node authentication required.")
    token = authorization[7:].strip()
    node = await NodeService.authenticate_node(db, token)
    if node is None:
        raise AuthenticationError("Invalid node credential.")
    return node


NodeDep = Annotated[Node, Depends(get_current_node)]
