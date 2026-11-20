import base64
import hashlib
import hmac
import os


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(f"parkvektor-kba-pii-v1:{secret}".encode()).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_pii(plaintext: str, secret: str) -> str:
    """
    Authenticated symmetric envelope encryption (HMAC-SHA256 CTR + Encrypt-then-MAC)
    for sensitive KBA § 39 StVG keeper names & addresses stored at rest.
    """
    key = _derive_key(secret)
    nonce = os.urandom(16)
    raw = plaintext.encode("utf-8")
    stream = _keystream(key, nonce, len(raw))
    ciphertext = bytes(a ^ b for a, b in zip(raw, stream, strict=True))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")
    return f"enc:v1:{token}"


def decrypt_pii(token: str, secret: str) -> str:
    if not token.startswith("enc:v1:"):
        return token
    raw = base64.urlsafe_b64decode(token.removeprefix("enc:v1:").encode("ascii"))
    nonce, mac, ciphertext = raw[:16], raw[16:48], raw[48:]
    key = _derive_key(secret)
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Encrypted PII integrity verification failed")
    stream = _keystream(key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))
    return plaintext.decode("utf-8")
