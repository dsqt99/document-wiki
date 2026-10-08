"""Base interface for all file parsers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseParser(ABC):
    """Abstract base class for document format parsers."""

    @abstractmethod
    async def parse(
        self,
        file_data: bytes,
        file_name: str,
        *,
        vision_provider: Optional[Any] = None,
        tracker: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Extract structured text from binary file data.

        Returns:
            List of page records: [{"content": str, "page_number": int, ...}]
        """
        pass
