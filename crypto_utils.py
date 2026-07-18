"""
Solo Leveling Fitness - Encryption Utilities
Encrypts/decrypts user-submitted API keys before storing them in the
database, using Fernet (AES-128 in CBC mode + HMAC authentication).

The encryption key itself lives OUTSIDE the database, in the
APP_ENCRYPTION_KEY environment variable. Losing that key means all
stored user API keys become unrecoverable (they'd just need to re-enter
them) -- it does NOT mean the database itself is compromised, since the
whole point is that ciphertext without the key is unreadable.

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Then set it as an environment variable (same way as GEMINI_API_KEY) and
never commit it to git or share it publicly -- .gitignore already covers
.env files, but double check if you store it differently.
"""

import os

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception


_cipher = None


def _get_cipher():
    """Lazily build the Fernet cipher from APP_ENCRYPTION_KEY"""
    global _cipher

    if _cipher is not None:
        return _cipher

    if Fernet is None:
        raise RuntimeError(
            'The "cryptography" package is not installed. '
            'Run: pip install cryptography'
        )

    key = os.environ.get('APP_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError(
            'APP_ENCRYPTION_KEY environment variable is not set. Generate one with:\n'
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            'Then set it as an environment variable before starting the server.'
        )

    _cipher = Fernet(key.encode() if isinstance(key, str) else key)
    return _cipher


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string (e.g. a user's API key) for storage"""
    cipher = _get_cipher()
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously-encrypted string"""
    cipher = _get_cipher()
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError('Could not decrypt value -- APP_ENCRYPTION_KEY may have changed')


def is_configured() -> bool:
    """Check whether encryption is ready to use (key present, package installed, key valid)"""
    try:
        _get_cipher()
        return True
    except Exception:
        # Covers: missing package, missing env var, AND a malformed/invalid
        # key value (e.g. wrong length or not proper base64) -- any of these
        # should mean "not configured", not an unhandled crash.
        return False
