"""
Unit tests for Storage protocol.
"""

import unittest

from storage.Storage import Storage


class TestStorage(unittest.TestCase):
    """Test cases for Storage protocol."""
    
    def test_storage_is_protocol(self) -> None:
        """Test that Storage is a Protocol."""
        # Protocols are structural types, so we mainly verify it exists
        self.assertTrue(hasattr(Storage, '__protocol_attrs__') or 
                       hasattr(Storage, '__abstractmethods__'))
