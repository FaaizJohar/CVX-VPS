"""cvx-agent CLI: enroll / serve."""

import argparse
import asyncio
import os
import ssl
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

CERT_DIR = Path("/etc/cvx-agent/tls")


def _ensure_tls_cert(port: int) -> tuple[str, str]:
    """Generate a self-signed cert for the agent API on first run."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert_file = CERT_DIR / "agent.crt"
    key_file = CERT_DIR / "agent.key"
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cvx-agent")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_file.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(key_file, 0o600)
    return str(cert_file), str(key_file)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from cvx_agent.config import AgentConfig

    cfg = AgentConfig.load()
    if cfg is None or not cfg.credential:
        print("[!] Not enrolled. Run: cvx-agent enroll --control-plane URL --token TOKEN")
        sys.exit(1)

    certfile, keyfile = _ensure_tls_cert(cfg.port)
    uvicorn.run(
        "cvx_agent.server:app",
        host="0.0.0.0",
        port=cfg.port,
        ssl_certfile=certfile,
        ssl_keyfile=keyfile,
        log_level="info",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="cvx-agent", description="CVX Node Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll_p = sub.add_parser("enroll", help="Enroll this node with the control plane")
    enroll_p.add_argument("--control-plane", required=os.environ.get("CVX_CONTROL_PLANE") is None,
                          default=os.environ.get("CVX_CONTROL_PLANE"))
    enroll_p.add_argument("--token", required=os.environ.get("CVX_ENROLL_TOKEN") is None,
                          default=os.environ.get("CVX_ENROLL_TOKEN"))

    sub.add_parser("serve", help="Run the agent server")

    args = parser.parse_args()
    if args.command == "enroll":
        from cvx_agent.enroll import enroll

        enroll(args.control_plane, args.token)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
