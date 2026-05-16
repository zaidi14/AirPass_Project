from typing import Optional, Set

try:
    from mfrc522 import MFRC522
except ImportError:
    MFRC522 = None


class RFIDReader:
    """Non-blocking RC522 reader wrapper with optional UID allow-list validation."""

    def __init__(self, valid_tags: Optional[Set[str]] = None):
        self.valid_tags = {tag.strip().upper() for tag in (valid_tags or set())}
        self._reader = None

        if MFRC522 is None:
            raise RuntimeError(
                "mfrc522 package not installed. Install with: pip install mfrc522"
            )

        self._reader = MFRC522()

    def read_tag(self) -> Optional[str]:
        """Returns UID string when a tag is present, otherwise None."""
        if self._reader is None:
            return None

        status, _ = self._reader.MFRC522_Request(self._reader.PICC_REQIDL)
        if status != self._reader.MI_OK:
            return None

        status, uid = self._reader.MFRC522_Anticoll()
        if status != self._reader.MI_OK or not uid:
            return None

        return "".join(f"{value:02X}" for value in uid)

    def is_valid_tag(self, uid: Optional[str]) -> bool:
        if not uid:
            return False

        if not self.valid_tags:
            return True

        return uid.upper() in self.valid_tags
