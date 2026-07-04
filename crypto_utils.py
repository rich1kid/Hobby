"""
Decrypts credentials stored by the Lovable/Supabase edge function.

IMPORTANT: The ENCRYPTION_KEY here must be the EXACT SAME key used by the
Supabase edge function that encrypted the data (mt5_accounts / pocket_option_accounts
tables). If Lovable auto-generated its own encryption secret, you need to either:
  (a) pull that same key and set it as ENCRYPTION_KEY here, or
  (b) re-point the edge function to use a shared key you control.

Expected stored format (adjust if your edge function differs):
  base64(iv[12 bytes] + ciphertext + authTag[16 bytes])
"""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")


def _get_key_bytes() -> bytes:
    if not ENCRYPTION_KEY:
        raise RuntimeError("ENCRYPTION_KEY env var is not set")
    # Supports either a raw 32-byte base64 key or a hex-encoded 32-byte key
    try:
        key = base64.b64decode(ENCRYPTION_KEY)
        if len(key) == 32:
            return key
    except Exception:
        pass
    try:
        key = bytes.fromhex(ENCRYPTION_KEY)
        if len(key) == 32:
            return key
    except Exception:
        pass
    raise RuntimeError("ENCRYPTION_KEY must decode to exactly 32 bytes (base64 or hex)")


def decrypt_value(encrypted_b64: str) -> str:
    """Decrypt a base64 string of iv(12) + ciphertext + tag(16) using AES-256-GCM."""
    key = _get_key_bytes()
    raw = base64.b64decode(encrypted_b64)
    iv, ciphertext_and_tag = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext_and_tag, None)
    return plaintext.decode("utf-8")
