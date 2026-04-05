"""Local DARWIN wallet files for repeatable PQ + EVM signing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt

from darwin_sim.sdk.accounts import DarwinAccount, create_account, public_account_from_dict

WALLET_FORMAT = "darwin-local-wallet-v1"


@dataclass(slots=True)
class DarwinWallet:
    label: str
    created_at: str
    account: DarwinAccount


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _secret_material_from_account(account: DarwinAccount) -> dict[str, str]:
    return {
        "pq_hot_sk": account.pq_hot_sk.hex(),
        "pq_cold_sk": account.pq_cold_sk.hex(),
        "evm_sk": account.evm_sk.hex(),
    }


def _account_from_wallet(public_account: dict, secret_material: dict) -> DarwinAccount:
    public = public_account_from_dict(public_account)
    return DarwinAccount(
        acct_id=public.acct_id,
        pq_hot_pk=public.pq_hot_pk,
        pq_hot_sk=bytes.fromhex(secret_material["pq_hot_sk"]),
        pq_cold_pk=public.pq_cold_pk,
        pq_cold_sk=bytes.fromhex(secret_material["pq_cold_sk"]),
        evm_addr=public.evm_addr,
        evm_sk=bytes.fromhex(secret_material["evm_sk"]),
        chain_id=public.chain_id,
        hot_capabilities=public.hot_capabilities,
        hot_value_limit_usd=public.hot_value_limit_usd,
        recovery_delay_sec=public.recovery_delay_sec,
    )


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise ValueError("wallet passphrase is required")
    return scrypt(passphrase.encode(), salt, key_len=32, N=2**14, r=8, p=1)


def _encrypt_secret_material(secret_material: dict[str, str], passphrase: str) -> dict[str, str]:
    import secrets

    plaintext = json.dumps(secret_material, sort_keys=True).encode()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = _derive_key(passphrase, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return {
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "tag": tag.hex(),
        "ciphertext": ciphertext.hex(),
    }


def _decrypt_secret_material(secret_box: dict[str, str], passphrase: str) -> dict[str, str]:
    if secret_box.get("cipher") != "AES-256-GCM" or secret_box.get("kdf") != "scrypt":
        raise ValueError("unsupported wallet encryption")
    salt = bytes.fromhex(secret_box["salt"])
    nonce = bytes.fromhex(secret_box["nonce"])
    tag = bytes.fromhex(secret_box["tag"])
    ciphertext = bytes.fromhex(secret_box["ciphertext"])
    key = _derive_key(passphrase, salt)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    return json.loads(plaintext.decode())


def create_wallet(
    *,
    label: str = "",
    chain_id: int = 1,
    hot_capabilities: int = 0xFF,
    hot_value_limit_usd: int = 50_000,
    recovery_delay_sec: int = 86400,
) -> DarwinWallet:
    account = create_account(
        chain_id=chain_id,
        hot_capabilities=hot_capabilities,
        hot_value_limit_usd=hot_value_limit_usd,
        recovery_delay_sec=recovery_delay_sec,
    )
    return DarwinWallet(
        label=label,
        created_at=_utc_now(),
        account=account,
    )


def wallet_public_dict(wallet: DarwinWallet) -> dict:
    return wallet.account.to_dict()


def save_wallet(wallet: DarwinWallet, path: str | Path, passphrase: str) -> Path:
    secret_box = _encrypt_secret_material(_secret_material_from_account(wallet.account), passphrase)
    document = {
        "format": WALLET_FORMAT,
        "label": wallet.label,
        "created_at": wallet.created_at,
        "public_account": wallet.account.to_dict(),
        "secret_box": secret_box,
    }
    wallet_path = Path(path)
    wallet_path.parent.mkdir(parents=True, exist_ok=True)
    wallet_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return wallet_path


def load_wallet_metadata(path: str | Path) -> dict:
    wallet_path = Path(path)
    data = json.loads(wallet_path.read_text())
    if data.get("format") != WALLET_FORMAT:
        raise ValueError(f"unsupported wallet format: {data.get('format')!r}")
    return data


def load_wallet_public_account(path: str | Path) -> DarwinAccount:
    return public_account_from_dict(load_wallet_metadata(path)["public_account"])


def load_wallet(path: str | Path, passphrase: str) -> DarwinWallet:
    data = load_wallet_metadata(path)
    secret_material = _decrypt_secret_material(data["secret_box"], passphrase)
    account = _account_from_wallet(data["public_account"], secret_material)
    return DarwinWallet(
        label=str(data.get("label", "")),
        created_at=str(data.get("created_at", "")),
        account=account,
    )
