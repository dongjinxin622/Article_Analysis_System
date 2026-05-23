"""
安全认证模块 - 密码哈希与验证（SHA-256 + bcrypt 两级哈希）
"""
import hashlib
import bcrypt

BCRYPT_SHA256_PREFIX = "$bcrypt-sha256$"


def hash_password(raw: str) -> str:
    """对密码进行 SHA-256 + bcrypt 两级哈希，结果带算法前缀"""
    sha256_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    hashed = bcrypt.hashpw(sha256_digest.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return f"{BCRYPT_SHA256_PREFIX}{hashed}"


def verify_password(raw: str, hashed: str) -> bool:
    """验证密码（兼容有前缀和无前缀两种格式）"""
    try:
        sha256_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if hashed.startswith(BCRYPT_SHA256_PREFIX):
            stored = hashed.removeprefix(BCRYPT_SHA256_PREFIX).encode("utf-8")
            return bcrypt.checkpw(sha256_digest.encode("utf-8"), stored)
        # 兼容旧格式（无前缀）
        return bcrypt.checkpw(sha256_digest.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, AttributeError):
        return False
