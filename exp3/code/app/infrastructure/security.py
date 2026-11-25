"""口令哈希与校验（PBKDF2-HMAC-SHA256），只依赖标准库。

存储格式：``pbkdf2_sha256$<迭代次数>$<盐 hex>$<摘要 hex>``。
种子数据用 :func:`derive_salt` 从登录名派生固定盐，保证「同一份种子脚本
跑两遍得到同一份库」，便于 S1-4 的行数断言与报告复现。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: PBKDF2 迭代次数；写进哈希串，便于日后只升不降
PBKDF2_ITERATIONS = 120_000

#: 算法标识
ALGORITHM = "pbkdf2_sha256"

#: 盐长度（字节）
SALT_BYTES = 16


def derive_salt(login_name: str) -> bytes:
    """从登录名派生确定性盐（仅用于种子与测试，生产口令请用 :func:`new_salt`）。"""
    digest = hashlib.sha256(f"hotel-booking::{login_name}".encode("utf-8")).digest()
    return digest[:SALT_BYTES]


def new_salt() -> bytes:
    """生成密码学安全的随机盐。"""
    return secrets.token_bytes(SALT_BYTES)


def hash_password(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    """计算口令哈希串。

    Args:
        password: 明文口令。
        salt: 盐（字节）。
        iterations: PBKDF2 迭代次数。

    Returns:
        形如 ``pbkdf2_sha256$120000$<盐 hex>$<摘要 hex>`` 的字符串。
    """
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """校验明文口令与哈希串是否匹配（常数时间比较）。"""
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
