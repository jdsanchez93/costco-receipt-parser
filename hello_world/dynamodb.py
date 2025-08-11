"""
DynamoDB module - imports from single_table.py for backward compatibility
"""

from single_table import (
    write_receipt_items as write_receipt_items_to_dynamodb,
    store_receipt_geometry,
    get_receipt_geometry,
    create_pending_user_receipt,
    convert_floats
)

# Export all functions for backward compatibility
__all__ = [
    'write_receipt_items_to_dynamodb',
    'store_receipt_geometry',
    'get_receipt_geometry',
    'create_pending_user_receipt',
    'convert_floats'
]