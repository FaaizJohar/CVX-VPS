import ipaddress
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps.auth import ActorDep, AdminDep, DbDep
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import IPAddress, IPStatus, Network, NetworkType
from app.schemas.user import ORMModel
from app.services.audit import record_audit

router = APIRouter(prefix="/networks", tags=["networks"])

ip_router = APIRouter(prefix="/ips", tags=["ips"])


class NetworkOut(ORMModel):
    id: uuid.UUID
    node_id: uuid.UUID
    name: str
    type: str
    description: str
    ipv4_subnet: str | None
    ipv6_subnet: str | None
    managed: bool
    is_default: bool


class NetworkCreate(BaseModel):
    node_id: uuid.UUID
    name: str = Field(min_length=2, max_length=64)
    type: NetworkType = NetworkType.BRIDGE
    description: str = ""
    ipv4_subnet: str | None = None
    ipv6_subnet: str | None = None


@router.get("", response_model=list[NetworkOut])
async def list_networks(actor: ActorDep, db: DbDep, node_id: uuid.UUID | None = None) -> list[NetworkOut]:
    q = select(Network)
    if node_id:
        q = q.where(Network.node_id == node_id)
    rows = (await db.execute(q.order_by(Network.name))).scalars().all()
    return [NetworkOut.model_validate(n) for n in rows]


@router.post("", status_code=201, response_model=NetworkOut)
async def create_network(body: NetworkCreate, admin: AdminDep, db: DbDep) -> NetworkOut:
    for subnet in (body.ipv4_subnet, body.ipv6_subnet):
        if subnet:
            try:
                ipaddress.ip_network(subnet)
            except ValueError as e:
                raise ValidationError(f"Invalid subnet {subnet!r}") from e
    dup = (
        await db.execute(
            select(Network).where(Network.node_id == body.node_id, Network.name == body.name)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ConflictError("A network with this name exists on the node.")
    network = Network(**body.model_dump())
    db.add(network)
    await db.flush()
    await record_audit(
        db, action="network.create", actor_user_id=str(admin.user.id),
        resource_type="network", resource_id=str(network.id), detail={"name": network.name},
    )
    return NetworkOut.model_validate(network)


# --- IP address management ---------------------------------------------------


class IPAddressOut(ORMModel):
    id: uuid.UUID
    node_id: uuid.UUID | None
    family: int
    address: str
    cidr: int | None
    gateway: str | None
    status: str
    vps_id: uuid.UUID | None
    assigned_at: object | None
    notes: str | None


class IPAddressCreate(BaseModel):
    node_id: uuid.UUID | None = None
    addresses: list[str] = Field(min_length=1, max_length=256)
    gateway: str | None = None
    notes: str | None = None


@ip_router.get("", response_model=list[IPAddressOut])
async def list_ips(
    actor: ActorDep,
    db: DbDep,
    node_id: uuid.UUID | None = None,
    status: IPStatus | None = None,
    family: int | None = Query(default=None, ge=4, le=6),
) -> list[IPAddressOut]:
    q = select(IPAddress)
    if node_id:
        q = q.where(IPAddress.node_id == node_id)
    if status:
        q = q.where(IPAddress.status == status)
    if family:
        q = q.where(IPAddress.family == family)
    rows = (await db.execute(q.order_by(IPAddress.address))).scalars().all()
    return [IPAddressOut.model_validate(i) for i in rows]


@ip_router.post("", status_code=201)
async def add_ips(body: IPAddressCreate, admin: AdminDep, db: DbDep) -> dict:
    added, skipped = 0, []
    seen: set[str] = set()
    for raw in body.addresses:
        addr = raw.strip()
        cidr = None
        if "/" in addr:
            addr, _, cidr_part = addr.partition("/")
            try:
                cidr = int(cidr_part)
            except ValueError as e:
                raise ValidationError(f"Invalid CIDR in {raw!r}") from e
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as e:
            raise ValidationError(f"Invalid IP address {raw!r}") from e
        if addr in seen:
            continue
        seen.add(addr)
        dup = (
            await db.execute(select(IPAddress).where(IPAddress.address == addr))
        ).scalar_one_or_none()
        if dup is not None:
            skipped.append(addr)
            continue
        db.add(
            IPAddress(
                node_id=body.node_id,
                family=ip.version,
                address=addr,
                cidr=cidr,
                gateway=body.gateway,
                status=IPStatus.AVAILABLE,
                notes=body.notes,
            )
        )
        added += 1
    await record_audit(
        db, action="ip.add", actor_user_id=str(admin.user.id),
        resource_type="ip", detail={"added": added, "skipped": skipped},
    )
    return {"added": added, "skipped": skipped}


@ip_router.post("/{ip_id}/reserve")
async def reserve_ip(ip_id: uuid.UUID, admin: AdminDep, db: DbDep) -> dict:
    rec = await db.get(IPAddress, ip_id)
    if rec is None:
        raise NotFoundError("IP not found.")
    if rec.status == IPStatus.ASSIGNED:
        raise ConflictError("IP is currently assigned to a VPS.")
    rec.status = IPStatus.RESERVED
    await record_audit(db, action="ip.reserve", actor_user_id=str(admin.user.id),
                       resource_type="ip", resource_id=str(ip_id))
    return {"status": rec.status.value}


@ip_router.post("/{ip_id}/release")
async def release_ip(ip_id: uuid.UUID, admin: AdminDep, db: DbDep) -> dict:
    rec = await db.get(IPAddress, ip_id)
    if rec is None:
        raise NotFoundError("IP not found.")
    rec.status = IPStatus.AVAILABLE
    rec.vps_id = None
    await record_audit(db, action="ip.release", actor_user_id=str(admin.user.id),
                       resource_type="ip", resource_id=str(ip_id))
    return {"status": "available"}
