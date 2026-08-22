import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, ConflictError, NotFoundError, ProviderError, ValidationError
from app.core.logging import get_logger
from app.core.security import new_uuid
from app.models import (
    IPAddress,
    IPStatus,
    Image,
    NODE_KIND_AGENT,
    Node,
    NodeStatus,
    User,
    UserRole,
    VPS,
    VPSStatus,
)
from app.providers.base import InstanceSpec
from app.schemas.vps import VPSCreate
from app.services.audit import record_audit, record_log
from app.services.node_service import NodeService

log = get_logger("cvx.vps")

RESERVED_CONFIG_PREFIXES = ("volatile.", "security.", "raw.", "boot.")


class VPSService:
    # ------------------------------------------------------------------ authz

    @staticmethod
    def can_access(user: User, vps: VPS) -> bool:
        if user.role in (UserRole.OWNER, UserRole.ADMIN):
            return True
        return vps.owner_id == user.id

    @staticmethod
    async def get_vps_checked(db: AsyncSession, *, vps_id: uuid.UUID, user: User) -> VPS:
        vps = await db.get(VPS, vps_id)
        if vps is None or vps.status == VPSStatus.DELETED:
            raise NotFoundError("VPS not found.")
        if not VPSService.can_access(user, vps):
            raise AuthorizationError()
        return vps

    # ------------------------------------------------------------- provisioning

    @staticmethod
    async def create_vps(
        db: AsyncSession, *, data: VPSCreate, owner: User, ip: str | None = None
    ) -> VPS:
        if data.deployment_mode == "local":
            node = await NodeService.get_or_create_local_node(db)
            if node is None:
                raise ValidationError(
                    "Local deployment is unavailable on this installation."
                )
        else:
            assert data.node_id is not None
            node = await db.get(Node, data.node_id)
        if node is None or node.status not in (NodeStatus.ONLINE, NodeStatus.MAINTENANCE):
            raise ValidationError("Target node is not online.")
        if node.status == NodeStatus.MAINTENANCE:
            raise ValidationError("Node is in maintenance mode.")
        expected_kind = "local" if data.deployment_mode == "local" else NODE_KIND_AGENT
        if getattr(node, "kind", NODE_KIND_AGENT) != expected_kind:
            raise ValidationError("Deployment mode does not match the target node.")

        image = await db.get(Image, data.image_id)
        if image is None or not image.enabled:
            raise ValidationError("Image is unavailable.")
        if data.cpu_limit < image.min_cpu or data.ram_mb < image.min_ram_mb or data.disk_gb < image.min_disk_gb:
            raise ValidationError(
                "Resources below the minimum for this image "
                f"(cpu>={image.min_cpu}, ram>={image.min_ram_mb}MB, disk>={image.min_disk_gb}GB)."
            )

        await VPSService._check_node_capacity(
            db, node=node, cpu=data.cpu_limit, ram_mb=data.ram_mb, disk_gb=data.disk_gb
        )

        # Unique provider ref — opaque to users.
        ref = f"cvx-{new_uuid().hex[:16]}"

        assigned_ipv4: IPAddress | None = None
        ipv4 = data.ipv4
        if ipv4:
            # Lock the address row (fast-path serialization on PostgreSQL); the
            # conditional UPDATE below is the authoritative atomic claim and
            # works even where FOR UPDATE is unavailable.
            assigned_ipv4 = (
                await db.execute(
                    select(IPAddress)
                    .where(
                        IPAddress.address == ipv4,
                        IPAddress.node_id == node.id,
                        IPAddress.status == IPStatus.AVAILABLE,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if assigned_ipv4 is None:
                raise ValidationError(f"IPv4 {ipv4} is not available on this node.")

        vps = VPS(
            node_id=node.id,
            owner_id=owner.id,
            image_id=image.id,
            name=data.name,
            hostname=data.hostname,
            provider_ref=ref,
            status=VPSStatus.PROVISIONING,
            deployment_mode=data.deployment_mode,
            cpu_limit=data.cpu_limit,
            ram_mb=data.ram_mb,
            swap_mb=data.swap_mb,
            disk_gb=data.disk_gb,
            process_limit=data.process_limit,
            network_name=data.network_name,
            dns_servers=data.dns_servers,
            ssh_keys=data.ssh_keys,
            password_auth_enabled=data.password_auth_enabled,
            root_password_set=bool(data.root_password) and data.password_auth_enabled,
            raw_config={},
        )
        db.add(vps)
        await db.flush()

        if assigned_ipv4 is not None:
            # Atomic claim: only succeeds if the address is still free at commit
            # time. A concurrent create loses here and surfaces a clean 422.
            from sqlalchemy import update as _update

            claim = await db.execute(
                _update(IPAddress)
                .where(
                    IPAddress.id == assigned_ipv4.id,
                    IPAddress.status == IPStatus.AVAILABLE,
                    IPAddress.vps_id.is_(None),
                )
                .values(status=IPStatus.ASSIGNED, vps_id=vps.id, assigned_at=func.now())
                .execution_options(synchronize_session=False)
            )
            if claim.rowcount != 1:
                raise ValidationError(f"IPv4 {ipv4} is not available on this node.")
            vps.ipv4 = assigned_ipv4.address

        try:
            provider = NodeService.provider_for(node)
            spec = InstanceSpec(
                name=ref,
                image_source=(
                    f"{image.source_remote}:{image.source_identifier}"
                    if image.source_type == "remote"
                    else image.source_identifier
                ),
                cpu_limit=data.cpu_limit,
                ram_mb=data.ram_mb,
                swap_mb=data.swap_mb,
                disk_gb=data.disk_gb,
                process_limit=data.process_limit,
                hostname=data.hostname,
                network_name=data.network_name,
                ipv4=data.ipv4,
                ipv6=data.ipv6,
                dns_servers=data.dns_servers,
                ssh_keys=data.ssh_keys,
                root_password=data.root_password if data.password_auth_enabled else None,
            )
            state = await provider.create_instance(spec)

            vps.status = VPSStatus.RUNNING
            ips = state.ips or {}
            if not vps.ipv4 and ips.get("eth0"):
                vps.ipv4 = ips["eth0"]
            vps.mac_address = (state.raw or {}).get("mac")
        except Exception as e:
            vps.status = VPSStatus.ERROR
            vps.provision_error = str(e)[:2000]
            if assigned_ipv4 is not None:
                assigned_ipv4.status = IPStatus.AVAILABLE
                assigned_ipv4.vps_id = None
            log.exception("vps provision failed ref=%s", ref)
            raise ProviderError("Provisioning failed on the node.") from e

        await record_audit(
            db,
            action="vps.create",
            actor_user_id=str(owner.id),
            resource_type="vps",
            resource_id=str(vps.id),
            node_id=str(node.id),
            detail={"name": vps.name, "image": image.alias},
            ip_address=ip,
        )
        await record_log(
            db,
            source="vps",
            message=f"VPS {vps.name} provisioned on node {node.name}",
            vps_id=str(vps.id),
            node_id=str(node.id),
        )
        return vps

    @staticmethod
    async def _check_node_capacity(
        db: AsyncSession, *, node: Node, cpu: int, ram_mb: int, disk_gb: int
    ) -> None:
        result = await db.execute(
            select(
                func.coalesce(func.sum(VPS.cpu_limit), 0),
                func.coalesce(func.sum(VPS.ram_mb), 0),
                func.coalesce(func.sum(VPS.disk_gb), 0),
            ).where(VPS.node_id == node.id, VPS.status.notin_([VPSStatus.DELETED, VPSStatus.ERROR]))
        )
        used_cpu, used_ram, used_disk = result.one()
        if node.cpu_cores is not None and used_cpu + cpu > node.cpu_cores * 4:
            raise ValidationError("CPU overcommit limit exceeded for this node.")
        if node.ram_total_mb is not None and used_ram + ram_mb > int(node.ram_total_mb * 1.5):
            raise ValidationError("Memory allocation exceeds node capacity headroom.")
        if node.storage_total_gb is not None and used_disk + disk_gb > node.storage_total_gb:
            raise ValidationError("Disk allocation exceeds node storage capacity.")

    # ---------------------------------------------------------------- lifecycle

    @staticmethod
    async def _provider(db: AsyncSession, vps: VPS):
        node = await db.get(Node, vps.node_id)
        if node is None:
            raise NotFoundError("Node not found.")
        return NodeService.provider_for(node), node

    @staticmethod
    async def lifecycle_action(
        db: AsyncSession,
        *,
        vps: VPS,
        action: str,
        actor: User,
        ip: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"start", "stop", "restart", "shutdown"}
        if action not in allowed:
            raise ValidationError(f"Unknown action {action!r}.")
        if vps.status == VPSStatus.DELETING:
            raise ConflictError("VPS is being deleted.")

        provider, node = await VPSService._provider(db, vps)
        try:
            if action == "start":
                result = await provider.start(vps.provider_ref)
                vps.status = VPSStatus.RUNNING
            elif action == "stop":
                result = await provider.stop(vps.provider_ref)
                vps.status = VPSStatus.STOPPED
            elif action == "restart":
                result = await provider.restart(vps.provider_ref)
                vps.status = VPSStatus.RUNNING
            else:  # shutdown — graceful ACPI
                result = await provider.shutdown(vps.provider_ref)
                vps.status = VPSStatus.STOPPED
        except Exception as e:
            log.warning("lifecycle %s failed vps=%s err=%s", action, vps.id, e)
            raise ProviderError(f"{action} failed on node {node.name}.") from e

        await record_audit(
            db,
            action=f"vps.{action}",
            actor_user_id=str(actor.id),
            resource_type="vps",
            resource_id=str(vps.id),
            node_id=str(node.id),
            ip_address=ip,
        )
        return {"id": str(vps.id), "status": vps.status.value, "action": action}

    @staticmethod
    async def delete_vps(
        db: AsyncSession, *, vps: VPS, actor: User, ip: str | None = None
    ) -> None:
        from datetime import UTC, datetime

        vps.status = VPSStatus.DELETING
        await db.flush()
        provider, node = await VPSService._provider(db, vps)
        try:
            await provider.delete_instance(vps.provider_ref)
        except Exception as e:
            vps.status = VPSStatus.ERROR
            vps.provision_error = f"delete failed: {e}"[:2000]
            raise ProviderError("Deletion failed on the node.") from e

        vps.status = VPSStatus.DELETED
        vps.deleted_at = datetime.now(UTC)

        # Release IPs.
        result = await db.execute(select(IPAddress).where(IPAddress.vps_id == vps.id))
        for rec in result.scalars():
            rec.status = IPStatus.AVAILABLE
            rec.vps_id = None

        await record_audit(
            db,
            action="vps.delete",
            actor_user_id=str(actor.id),
            resource_type="vps",
            resource_id=str(vps.id),
            node_id=str(node.id),
            detail={"name": vps.name},
            ip_address=ip,
        )

    # ------------------------------------------------------------------ config

    @staticmethod
    async def update_raw_config(
        db: AsyncSession, *, vps: VPS, config: dict[str, str], actor: User
    ) -> dict[str, Any]:
        for key in config:
            if any(key.startswith(p) for p in RESERVED_CONFIG_PREFIXES) and actor.role not in (
                UserRole.OWNER,
                UserRole.ADMIN,
            ):
                raise AuthorizationError(f"Config key {key!r} requires admin privileges.")
        provider, _node = await VPSService._provider(db, vps)
        result = await provider.set_config(vps.provider_ref, config)
        vps.raw_config = {**(vps.raw_config or {}), **config}
        await record_audit(
            db,
            action="vps.config.update",
            actor_user_id=str(actor.id),
            resource_type="vps",
            resource_id=str(vps.id),
            detail={"keys": sorted(config.keys())},
        )
        return result

    # ------------------------------------------------------------------ listing

    @staticmethod
    async def list_vps(
        db: AsyncSession,
        *,
        user: User,
        page: int = 1,
        page_size: int = 25,
        node_id: uuid.UUID | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[VPS], int]:
        q = select(VPS).where(VPS.status != VPSStatus.DELETED)
        if user.role not in (UserRole.OWNER, UserRole.ADMIN):
            q = q.where(VPS.owner_id == user.id)
        if node_id:
            q = q.where(VPS.node_id == node_id)
        if status:
            q = q.where(VPS.status == status)
        if search:
            # Escape LIKE wildcards from user input; match literal text.
            safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            q = q.where(VPS.name.ilike(f"%{safe}%", escape="\\"))
        total = (
            await db.execute(select(func.count()).select_from(q.subquery()))
        ).scalar_one()
        rows = await db.execute(
            q.order_by(VPS.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars()), total
