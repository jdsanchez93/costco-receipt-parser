"""
Receipt Members module - imports from single_table.py for backward compatibility
"""

from single_table import (
    add_authenticated_user_to_receipt,
    add_placeholder_user_to_receipt,
    get_receipt_members,
    get_user_receipts,
    claim_placeholder_user
)

# Export all functions for backward compatibility
__all__ = [
    'add_authenticated_user_to_receipt',
    'add_placeholder_user_to_receipt',
    'get_receipt_members',
    'get_user_receipts',
    'claim_placeholder_user'
]