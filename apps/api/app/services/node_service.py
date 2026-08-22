import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    expiry,
    generate_enrollment_token,
    generate_node_credential,
    hash_token,
    utcnow,
)
from app.core.logging import get_logger
from app.models import EnrollmentToken, Node, NodeStatus
from app.providers.agent_client import AgentClient
from app.providers.lxd import LXDProvider
from app.schemas.node import AgentHello, AgentHeartbeat, NodeCreate

log = get_logger("cvx.node")

# Transitional states older than this are considered crashed (recovered by reconcile).
_TRANSITIONAL_TIMEOUT_SECONDS = 30 * 60


class NodeService:
    @staticmethod
    async def create_node(
        db: AsyncSession, *, data: NodeCreate, created_by_id: uuid.UUID
    ) -> tuple[Node, str]:
        existing = (
            await db.execute(select(Node).where(Node.name == data.name))
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Node name {data.name!r} already exists.")

        node = Node(
            name=data.name,
            location=data.location,
            hostname=data.hostname,
            public_ip=data.public_ip,
            description=data.description,
            status=NodeStatus.PENDING,
        )
        db.add(node)
        await db.flush()

        token = await NodeService.issue_enrollment_token(db, node=node, created_by_id=created_by_id)
        return node, token

    @staticmethod
    async def issue_enrollment_token(
        db: AsyncSession, *, node: Node, created_by_id: uuid.UUID | None = None
    ) -> str:
        settings = get_settings()
        token = generate_enrollment_token()
        db.add(
            EnrollmentToken(
                node_id=node.id,
                token_hash=hash_token(token),
                expires_at=expiry(settings.enrollment_token_ttl_seconds),
                created_by_id=created_by_id,
            )
        )
        return token

    @staticmethod
    async def revoke_enrollment_tokens(db: AsyncSession, *, node_id: uuid.UUID) -> int:
        result = await db.execute(select(EnrollmentToken).where(EnrollmentToken.node_id == node_id))
        n = 0
        for t in result.scalars():
            if t.revoked_at is None and t.used_at is None:
                t.revoked_at = utcnow()
                n += 1
        return n

    @staticmethod
    async def enroll(
        db: AsyncSession, *, token: str, hello: AgentHello
    ) -> tuple[Node, str]:
        """Exchange a single-use enrollment token for a permanent node credential."""
        rec = (
            await db.execute(
                select(EnrollmentToken).where(EnrollmentToken.token_hash == hash_token(token))
            )
        ).scalar_one_or_none()
        if rec is None or not rec.is_usable:
            raise AuthenticationError("Invalid, expired, or already-used enrollment token.")

        node = await db.get(Node, rec.node_id)
        if node is None or node.status in (NodeStatus.DISABLED, NodeStatus.REMOVED):
            raise AuthenticationError("Node is not eligible for enrollment.")

        if hello.lxd_version is None:
            raise ValidationError("LXD was not detected on this machine. Install LXD first.")

        # Atomically claim the single-use token. The conditional UPDATE serializes
        # concurrent enroll attempts at the database level — only one wins.
        claimed = await db.execute(
            update(EnrollmentToken)
            .where(
                EnrollmentToken.id == rec.id,
                EnrollmentToken.used_at.is_(None),
                EnrollmentToken.revoked_at.is_(None),
                EnrollmentToken.expires_at > utcnow(),
            )
            .values(used_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            raise AuthenticationError("Invalid, expired, or already-used enrollment token.")

        # Issue permanent credential; store hashed + encrypted, return plaintext once.
        credential = generate_node_credential()
        node.credential_hash = hash_token(credential)
        node.credential_encrypted = encrypt_secret(credential)
        node.status = NodeStatus.ONLINE
        node.enrolled_at = utcnow()
        node.last_heartbeat_at = utcnow()
        node.agent_version = hello.agent_version
        node.hostname = hello.hostname or node.hostname
        node.os_name = hello.os_name
        node.os_version = hello.os_version
        node.kernel_version = hello.kernel_version
        node.architecture = hello.architecture
        node.lxd_version = hello.lxd_version
        node.cpu_model = hello.cpu_model
        node.cpu_cores = hello.cpu_cores
        node.ram_total_mb = hello.ram_total_mb
        node.storage_total_gb = hello.storage_total_gb
        node.storage_driver = hello.storage_driver

        rec.used_at = utcnow()
        await db.flush()
        log.info("node enrolled id=%s name=%s", node.id, node.name)
        return node, credential

    @staticmethod
    async def authenticate_node(db: AsyncSession, credential: str) -> Node | None:
        node = (
            await db.execute(
                select(Node).where(Node.credential_hash == hash_token(credential))
            )
        ).scalar_one_or_none()
        if node is None or node.status in (NodeStatus.DISABLED, NodeStatus.REMOVED):
            return None
        return node

    @staticmethod
    async def heartbeat(db: AsyncSession, *, node: Node, hb: AgentHeartbeat) -> dict:
        from app.models import VPS, VPSStatus

        node.last_heartbeat_at = utcnow()
        if node.status in (NodeStatus.OFFLINE, NodeStatus.PENDING):
            node.status = NodeStatus.ONLINE
        node.agent_version = hb.agent_version
        if hb.lxd_version:
            node.lxd_version = hb.lxd_version
        node.cpu_percent = hb.cpu_percent
        node.ram_used_mb = hb.ram_used_mb
        if hb.ram_total_mb:
            node.ram_total_mb = hb.ram_total_mb
        node.storage_used_gb = hb.storage_used_gb
        if hb.storage_total_gb:
            node.storage_total_gb = hb.storage_total_gb
        node.load1 = hb.load1
        node.uptime_seconds = hb.uptime_seconds

        # Reconcile instance states reported by the agent.
        known = {
            r[0]: r[1]
            for r in (
                await db.execute(
                    select(VPS.provider_ref, VPS.status).where(VPS.node_id == node.id)
                )
            ).all()
        }
        reported = {i.get("name"): i.get("status") for i in hb.instances}
        changed = 0
        transitional = (VPSStatus.CREATING, VPSStatus.PROVISIONING, VPSStatus.DELETING)
        for ref, current in known.items():
            reported_status = reported.get(ref)
            if reported_status is None:
                # Instance vanished from the node. Transitional rows are owned by an
                # in-flight create/delete; anything else is stale and must surface.
                if current not in transitional and current != VPSStatus.DELETED:
                    row = await db.execute(
                        select(VPS).where(VPS.provider_ref == ref, VPS.node_id == node.id)
                    )
                    vps = row.scalar_one_or_none()
                    if vps is not None:
                        vps.status = VPSStatus.ERROR
                        vps.provision_error = "missing_on_node"
                        changed += 1
                continue
            new_status = _map_instance_status(reported_status)
            if new_status is not None and new_status != current:
                row = await db.execute(
                    select(VPS).where(VPS.provider_ref == ref, VPS.node_id == node.id)
                )
                vps = row.scalar_one_or_none()
                if vps is not None and vps.status not in transitional:
                    vps.status = new_status
                    changed += 1

        # Recover rows stuck in transitional states (crashed create/delete flows).
        stuck_cutoff = datetime.now(UTC) - timedelta(seconds=_TRANSITIONAL_TIMEOUT_SECONDS)
        stuck_rows = (
            await db.execute(
                select(VPS).where(
                    VPS.node_id == node.id,
                    VPS.status.in_(transitional),
                    VPS.updated_at < stuck_cutoff,
                )
            )
        ).scalars().all()
        for vps in stuck_rows:
            if vps.status == VPSStatus.DELETING and vps.provider_ref not in reported:
                # Instance confirmed gone: complete the deletion and release IPs.
                vps.status = VPSStatus.DELETED
                from app.models import IPAddress, IPStatus  # local import avoids cycles

                ips = await db.execute(select(IPAddress).where(IPAddress.vps_id == vps.id))
                for rec in ips.scalars():
                    rec.status = IPStatus.AVAILABLE
                    rec.vps_id = None
                changed += 1
            elif vps.status in (VPSStatus.CREATING, VPSStatus.PROVISIONING):
                vps.status = VPSStatus.ERROR
                vps.provision_error = "provisioning_timeout"
                changed += 1
            elif vps.status == VPSStatus.DELETING:
                # Still present on the node after timeout — surface for operator action.
                vps.status = VPSStatus.ERROR
                vps.provision_error = "deletion_timeout"
                changed += 1

        await db.flush()
        return {"ok": True, "instances_synced": changed}

    @staticmethod
    def provider_for(node: Node) -> LXDProvider:
        """Build an authenticated provider handle for a node.

        Raises if the node has no usable credential (never enrolled / rotated).
        """
        if not node.credential_encrypted:
            raise NotFoundError("Node is not enrolled.")
        credential = decrypt_secret(node.credential_encrypted)
        client = AgentClient.for_node(node.public_ip, credential)
        return LXDProvider(client)

    @staticmethod
    async def get_node(db: AsyncSession, node_id: uuid.UUID) -> Node:
        node = await db.get(Node, node_id)
        if node is None or node.status == NodeStatus.REMOVED:
            raise NotFoundError("Node not found.")
        return node

    @staticmethod
    def effective_status(node: Node) -> str:
        settings = get_settings()
        current = node.status.value if isinstance(node.status, NodeStatus) else str(node.status)
        if current == NodeStatus.ONLINE.value and node.last_heartbeat_at:
            from app.core.security import ensure_aware

            age = (datetime.now(UTC) - ensure_aware(node.last_heartbeat_at)).total_seconds()
            if age > settings.node_offline_after_seconds:
                return NodeStatus.OFFLINE.value
        return current


def _map_instance_status(lxd_status: str | None) -> str | None:
    if lxd_status is None:
        return None
    mapping = {
        "Running": "running",
        "Stopped": "stopped",
        "Frozen": "frozen",
        "Error": "error",
    }
    return mapping.get(lxd_status)
