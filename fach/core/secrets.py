"""Passwort im Passwortspeicher des Systems: Windows-Anmeldeinformationsverwaltung bzw. macOS-Schlüsselbund.

In der gebauten App findet `keyring` sein Backend nicht immer selbst (Entry-Points fehlen
im PyInstaller-Paket) – deshalb wird es hier ausdrücklich gewählt.
"""

from __future__ import annotations

import sys
from typing import Protocol


class SecretStore(Protocol):
    def get(self, service: str, user: str) -> str | None: ...
    def set(self, service: str, user: str, password: str) -> None: ...
    def delete(self, service: str, user: str) -> None: ...


class KeyringStore:
    def __init__(self) -> None:
        import keyring

        if sys.platform == "win32":
            from keyring.backends.Windows import WinVaultKeyring

            keyring.set_keyring(WinVaultKeyring())
        elif sys.platform == "darwin":
            from keyring.backends.macOS import Keyring

            keyring.set_keyring(Keyring())
        self._kr = keyring

    def get(self, service: str, user: str) -> str | None:
        return self._kr.get_password(service, user)

    def set(self, service: str, user: str, password: str) -> None:
        self._kr.set_password(service, user, password)

    def delete(self, service: str, user: str) -> None:
        from keyring.errors import PasswordDeleteError

        try:
            self._kr.delete_password(service, user)
        except PasswordDeleteError:
            pass


class MemoryStore:
    """Für Tests und den Demo-Modus – nichts verlässt den Arbeitsspeicher."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get(self, service: str, user: str) -> str | None:
        return self._data.get((service, user))

    def set(self, service: str, user: str, password: str) -> None:
        self._data[(service, user)] = password

    def delete(self, service: str, user: str) -> None:
        self._data.pop((service, user), None)


def password_store_name() -> str:
    """So heißt der Speicher für Menschen – wird im Onboarding angezeigt."""
    if sys.platform == "win32":
        return "der Windows-Anmeldeinformationsverwaltung"
    if sys.platform == "darwin":
        return "deinem macOS-Schlüsselbund"
    return "dem Passwortspeicher deines Systems"
