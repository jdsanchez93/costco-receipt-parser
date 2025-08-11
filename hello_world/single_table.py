"""
Single Table Design for Costco Receipt Parser
This module consolidates all DynamoDB operations into a single table

Table Access Patterns:
1. Receipt Items: PK=RECEIPT#{receipt_id}, SK=ITEM#{item_id}
2. Receipt Members: PK=RECEIPT#{receipt_id}, SK=USER#{user_id}
3. User Receipts: PK=USER#{user_id}, SK=RECEIPT#{receipt_id}
4. Share Tokens: PK=SHARE#{token}, SK=RECEIPT#{receipt_id}
5. Receipt Geometry: PK=RECEIPT#{receipt_id}, SK=GEOMETRY#{field}#{type}

GSI1: For user lookups
- GSI1PK=USER#{user_id}, GSI1SK=RECEIPT#{receipt_id}

GSI2: For receipt share lookups  
- GSI2PK=RECEIPT#{receipt_id}, GSI2SK=SHARE#{token}
"""

from datetime import datetime, timedelta
from decimal import Decimal
import boto3
import boto3.dynamodb.conditions
import uuid
import secrets
import os

dynamodb = boto3.resource('dynamodb')

def get_table_name():
    """Get the table name from environment variable"""
    # TABLE_NAME is set in the Lambda environment variables
    return os.environ.get('TABLE_NAME', 'costco-receipt-parser-main')

def get_table():
    """Get the main DynamoDB table"""
    return dynamodb.Table(get_table_name())

def convert_floats(obj):
    """Convert float values to Decimal for DynamoDB"""
    if isinstance(obj, list):
        return [convert_floats(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj

# ==================== RECEIPT ITEMS ====================

def write_receipt_items(receipt_id, items, assigned_users):
    """Write receipt items to the table"""
    table = get_table()
    
    for item in items:
        pk = f"RECEIPT#{receipt_id}"
        sk = f"ITEM#{item['item_id']}"
        table.put_item(
            Item=convert_floats({
                'PK': pk,
                'SK': sk,
                'entity_type': 'RECEIPT_ITEM',
                'item_number': item['item_number'],
                'item_name': item['item'],
                'price': item['price'],
                'discount': item['discount'],
                'receipt_id': receipt_id,
                'assigned_users': assigned_users,
                'created_at': datetime.now().isoformat()
            }),
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )

def get_receipt_items(receipt_id):
    """Get all items for a receipt"""
    table = get_table()
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'RECEIPT#{receipt_id}') &
                              boto3.dynamodb.conditions.Key('SK').begins_with('ITEM#')
    )
    
    return response.get('Items', [])

# ==================== RECEIPT MEMBERS ====================

def add_authenticated_user_to_receipt(receipt_id, user_id, display_name, email, added_by_user_id, role='member'):
    """Add an authenticated user as a member of a receipt"""
    table = get_table()
    
    member_record = {
        'PK': f'RECEIPT#{receipt_id}',
        'SK': f'USER#{user_id}',
        'GSI1PK': f'USER#{user_id}',
        'GSI1SK': f'RECEIPT#{receipt_id}',
        'entity_type': 'RECEIPT_MEMBER',
        'user_type': 'authenticated',
        'display_name': display_name,
        'email': email,
        'user_id': user_id,
        'receipt_id': receipt_id,
        'role': role,  # 'owner', 'member', 'viewer'
        'added_by': added_by_user_id,
        'added_at': datetime.now().isoformat()
    }
    
    table.put_item(
        Item=member_record,
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )
    
    # Note: No longer creating duplicate USER_RECEIPT record
    # GSI1 handles user lookups efficiently
    
    return member_record

def add_placeholder_user_to_receipt(receipt_id, display_name, added_by_user_id):
    """Add a placeholder user to a receipt"""
    table = get_table()
    
    placeholder_id = str(uuid.uuid4())
    
    member_record = {
        'PK': f'RECEIPT#{receipt_id}',
        'SK': f'USER#{placeholder_id}',
        'GSI1PK': f'USER#{placeholder_id}',
        'GSI1SK': f'RECEIPT#{receipt_id}',
        'entity_type': 'RECEIPT_MEMBER',
        'user_type': 'placeholder',
        'display_name': display_name,
        'placeholder_id': placeholder_id,
        'receipt_id': receipt_id,
        'added_by': added_by_user_id,
        'added_at': datetime.now().isoformat()
    }
    
    table.put_item(
        Item=member_record,
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )
    
    # Note: No longer creating separate placeholder user record
    # GSI1 handles user lookups efficiently
    
    return member_record

def get_receipt_members(receipt_id):
    """Get all members of a receipt"""
    table = get_table()
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'RECEIPT#{receipt_id}') &
                              boto3.dynamodb.conditions.Key('SK').begins_with('USER#')
    )
    
    return response.get('Items', [])

def get_user_receipts(user_id):
    """Get all receipts for a user"""
    table = get_table()
    
    # Use GSI1 for efficient user lookups
    response = table.query(
        IndexName='GSI1',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(f'USER#{user_id}')
    )
    
    return response.get('Items', [])

def claim_placeholder_user(placeholder_id, auth_user_id, display_name, email):
    """Claim a placeholder user by converting it to an authenticated user"""
    table = get_table()
    
    # Get all receipts the placeholder is on
    placeholder_receipts = get_user_receipts(placeholder_id)
    
    updated_records = []
    
    for receipt_membership in placeholder_receipts:
        receipt_id = receipt_membership.get('receipt_id') or receipt_membership['GSI1SK'].replace('RECEIPT#', '')
        
        # Delete old placeholder membership
        table.delete_item(
            Key={
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'USER#{placeholder_id}'
            }
        )
        
        # Note: No separate placeholder records to delete in clean design
        
        # Add authenticated user membership
        new_record = add_authenticated_user_to_receipt(
            receipt_id=receipt_id,
            user_id=auth_user_id,
            display_name=display_name,
            email=email,
            added_by_user_id=receipt_membership.get('added_by', auth_user_id)
        )
        new_record['claimed_from_placeholder'] = placeholder_id
        new_record['claimed_at'] = datetime.now().isoformat()
        
        updated_records.append(new_record)
    
    return updated_records

def update_receipt_member_details(receipt_id, user_id, display_name=None, email=None):
    """
    Update display name and/or email for a receipt member
    
    Args:
        receipt_id: ID of the receipt
        user_id: User ID to update
        display_name: New display name (optional)
        email: New email (optional)
        
    Returns:
        dict: Updated member record
    """
    table = get_table()
    
    update_expressions = []
    expression_values = {}
    
    if display_name is not None:
        update_expressions.append("display_name = :name")
        expression_values[":name"] = display_name
    
    if email is not None:
        update_expressions.append("email = :email")
        expression_values[":email"] = email
    
    if not update_expressions:
        # Nothing to update
        return None
    
    update_expressions.append("updated_at = :timestamp")
    expression_values[":timestamp"] = datetime.now().isoformat()
    
    try:
        response = table.update_item(
            Key={
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'USER#{user_id}'
            },
            UpdateExpression=f'SET {", ".join(update_expressions)}',
            ExpressionAttributeValues=expression_values,
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)',
            ReturnValues='ALL_NEW'
        )
        
        return response.get('Attributes', {})
        
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None

# ==================== RECEIPT SHARES ====================

def create_receipt_share(receipt_id, owner_user_id, expires_in_days=30):
    """Create a share token for a receipt"""
    table = get_table()
    
    share_token = secrets.token_urlsafe(32)
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=expires_in_days)
    expires_at_timestamp = int(expires_at.timestamp())
    
    share_record = {
        'PK': f'SHARE#{share_token}',
        'SK': f'RECEIPT#{receipt_id}',
        'GSI2PK': f'RECEIPT#{receipt_id}',
        'GSI2SK': f'SHARE#{share_token}',
        'entity_type': 'RECEIPT_SHARE',
        'receipt_id': receipt_id,
        'owner_user_id': owner_user_id,
        'share_token': share_token,
        'created_at': created_at.isoformat(),
        'expires_at': expires_at_timestamp,
        'is_active': True,
        'current_uses': 0
    }
    
    table.put_item(
        Item=share_record,
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )
    
    return share_record

def get_receipt_from_share_token(share_token):
    """Get receipt information from a share token"""
    table = get_table()
    
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'SHARE#{share_token}')
        )
        
        items = response.get('Items', [])
        if not items:
            return None
            
        share_record = items[0]
        
        # Check if share is still active
        if not share_record.get('is_active', False):
            return None
            
        # TTL will automatically handle expiration, but we can check here too
        expires_at = share_record.get('expires_at', 0)
        if expires_at < int(datetime.now().timestamp()):
            return None
            
        return share_record
        
    except Exception:
        return None

def get_active_shares_for_receipt(receipt_id):
    """Get all active shares for a receipt"""
    table = get_table()
    
    response = table.query(
        IndexName='GSI2',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI2PK').eq(f'RECEIPT#{receipt_id}') & 
                              boto3.dynamodb.conditions.Key('GSI2SK').begins_with('SHARE#')
    )
    
    # Filter out inactive shares
    active_shares = [
        share for share in response.get('Items', [])
        if share.get('is_active', False)
    ]
    
    return active_shares

def increment_share_usage(share_token, receipt_id):
    """Increment the usage counter for a share token"""
    table = get_table()
    
    try:
        response = table.update_item(
            Key={
                'PK': f'SHARE#{share_token}',
                'SK': f'RECEIPT#{receipt_id}'
            },
            UpdateExpression='ADD current_uses :inc SET updated_at = :timestamp',
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK) AND is_active = :active',
            ExpressionAttributeValues={
                ':inc': 1,
                ':timestamp': datetime.now().isoformat(),
                ':active': True
            },
            ReturnValues='ALL_NEW'
        )
        
        return response.get('Attributes', {})
        
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None

def deactivate_share(share_token, receipt_id):
    """Deactivate a share token"""
    table = get_table()
    
    try:
        table.update_item(
            Key={
                'PK': f'SHARE#{share_token}',
                'SK': f'RECEIPT#{receipt_id}'
            },
            UpdateExpression='SET is_active = :inactive, updated_at = :timestamp',
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)',
            ExpressionAttributeValues={
                ':inactive': False,
                ':timestamp': datetime.now().isoformat()
            }
        )
        return True
        
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False

# ==================== RECEIPT GEOMETRY ====================

def store_receipt_geometry(receipt_id, special_fields):
    """Store geometry data for special fields (subtotal, total, tax)"""
    if not special_fields:
        return
        
    table = get_table()
    
    for field_name, field_data in special_fields.items():
        # Store label geometry
        table.put_item(
            Item=convert_floats({
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'GEOMETRY#{field_name.upper()}#LABEL',
                'entity_type': 'RECEIPT_GEOMETRY',
                'receipt_id': receipt_id,
                'field_name': field_name,
                'field_type': 'label',
                'text': field_data['label_text'],
                'confidence': field_data['confidence'],
                'bounding_box': field_data['label_geometry']['BoundingBox'],
                'polygon': field_data['label_geometry']['Polygon'],
                'created_at': datetime.now().isoformat()
            }),
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )
        
        # Store value geometry
        table.put_item(
            Item=convert_floats({
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'GEOMETRY#{field_name.upper()}#VALUE',
                'entity_type': 'RECEIPT_GEOMETRY',
                'receipt_id': receipt_id,
                'field_name': field_name,
                'field_type': 'value',
                'text': field_data['value_text'],
                'confidence': field_data['confidence'],
                'bounding_box': field_data['value_geometry']['BoundingBox'],
                'polygon': field_data['value_geometry']['Polygon'],
                'created_at': datetime.now().isoformat()
            }),
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )

def get_receipt_geometry(receipt_id):
    """Retrieve geometry data for a receipt"""
    table = get_table()
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'RECEIPT#{receipt_id}') &
                              boto3.dynamodb.conditions.Key('SK').begins_with('GEOMETRY#')
    )
    
    fields = {}
    for item in response.get('Items', []):
        field_name = item['field_name']
        field_type = item['field_type']
        
        if field_name not in fields:
            fields[field_name] = {}
            
        fields[field_name][field_type] = {
            'text': item['text'],
            'confidence': float(item['confidence']),
            'bounding_box': {
                'Width': float(item['bounding_box']['Width']),
                'Height': float(item['bounding_box']['Height']),
                'Left': float(item['bounding_box']['Left']),
                'Top': float(item['bounding_box']['Top'])
            },
            'polygon': [
                {
                    'X': float(point['X']),
                    'Y': float(point['Y'])
                }
                for point in item['polygon']
            ]
        }
    
    return fields

