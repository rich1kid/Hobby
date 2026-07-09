"""
Decrypts credentials stored by the Lovable/Supabase edge function
(supabase/functions/telegram-webhook/index.ts).

Matches that implementation exactly:
- Key = SHA-256 hash of the UTF-8 text of ENCRYPTION_KEY (not raw key bytes)
- Stored format = "{base64(iv)}:{base64(ciphertext+authTag)}" (colon-separated,
  not a single concatenated blob)
"""
import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY_RAW = os.environ.get("ENCRYPTION_KEY", "")


def _get_key_bytes() -> bytes:
    if not ENCRYPTION_KEY_RAW:
        raise RuntimeError("ENCRYPTION_KEY env var is not set")
    # Same derivation as the edge function: SHA-256 of the UTF-8 text value
    return hashlib.sha256(ENCRYPTION_KEY_RAW.encode("utf-8")).digest()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a 'base64(iv):base64(ciphertext+tag)' string using AES-256-GCM."""
    key = _get_key_bytes()
    iv_b64, ct_b64 = encrypted.split(":", 1)
    iv = base64.b64decode(iv_b64)
    ciphertext_and_tag = base64.b64decode(ct_b64)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext_and_tag, None)
    return plaintext.decode("utf-8")
