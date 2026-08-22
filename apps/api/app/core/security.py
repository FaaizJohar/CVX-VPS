"""Cryptographic primitives: password hashing, token generation/hashing.

Design rules enforced here:
- Passwords use Argon2id.
- Opaque tokens (sessions, enrollment, API keys) are stored only as SHA-256 hashes.
- Node credentials are high-entropy and stored hashed; the plaintext is shown once.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()

# 32 bytes of entropy -> 43 char url-safe string
TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_aware(dt: datetime) -> datetime:
    """Normalize DB-provided datetimes to UTC-aware for safe comparison."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def expiry(seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


def generate_node_credential() -> str:
    """Credential used by an enrolled node agent to authenticate.

    Format: cvxnode_<node_id_short>_<secret> — self-describing, high entropy.
    """
    return f"cvxnode_{secrets.token_hex(8)}_{secrets.token_urlsafe(TOKEN_BYTES)}"


def generate_enrollment_token() -> str:
    return f"cvxenroll_{secrets.token_urlsafe(TOKEN_BYTES)}"


def generate_api_key() -> tuple[str, str]:
    """Returns (plaintext_key, key_prefix)."""
    settings = get_settings()
    secret = secrets.token_urlsafe(TOKEN_BYTES)
    prefix = f"{settings.api_key_prefix}_{secrets.token_hex(4)}"
    return f"{prefix}_{secret}", prefix


# --- Secret encryption at rest -------------------------------------------
#
# Node credentials must be usable by the control plane to call agents, but
# never stored in plaintext. We derive an AES key (via Fernet) from the
# application secret using HKDF-SHA256.


def _fernet() -> Fernet:
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    salt = b"cvx-node-credential-v1"
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"cvx-secret-box",
    )
    key = hkdf.derive(get_settings().secret_key.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Cannot decrypt secret: wrong SECRET_KEY?") from e
