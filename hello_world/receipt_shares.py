"""
Receipt Shares module - imports from single_table.py for backward compatibility
"""

from single_table import (
    create_receipt_share,
    get_receipt_from_share_token,
    get_active_shares_for_receipt,
    increment_share_usage,
    deactivate_share
)

# Export all functions for backward compatibility
__all__ = [
    'create_receipt_share',
    'get_receipt_from_share_token',
    'get_active_shares_for_receipt',
    'increment_share_usage',
    'deactivate_share'
]