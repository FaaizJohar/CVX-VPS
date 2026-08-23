from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    agent,
    apikeys,
    auth,
    console,
    images,
    jobs,
    logs,
    metrics,
    networks,
    nodes,
    snapshots,
    users,
    vps,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(nodes.router)
api_router.include_router(agent.router)
api_router.include_router(vps.router)
api_router.include_router(snapshots.router)
api_router.include_router(metrics.router)
api_router.include_router(images.router)
api_router.include_router(networks.router)
api_router.include_router(networks.ip_router)
api_router.include_router(jobs.router)
api_router.include_router(logs.router)
api_router.include_router(apikeys.router)
api_router.include_router(admin.router)
