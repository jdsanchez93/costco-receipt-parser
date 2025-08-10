from datetime import datetime
import boto3
import boto3.dynamodb.conditions
import uuid
import os

dynamodb = boto3.resource('dynamodb')

def get_table_name():
    """Get the table name based on stack name"""
    stack_name = os.environ.get('AWS_STACK_NAME', 'costco-receipt-parser')
    return f"{stack_name}-receipt-members"

def add_authenticated_user_to_receipt(receipt_id, user_id, display_name, email, added_by_user_id):
    """
    Add an authenticated user to a receipt
    
    Args:
        receipt_id: ID of the receipt
        user_id: Auth0 user ID (e.g., "auth0|abc123")
        display_name: User's display name
        email: User's email address
        added_by_user_id: User ID of who added this user
        
    Returns:
        dict: The created member record
    """
    table = dynamodb.Table(get_table_name())
    
    member_record = {
        'PK': f'RECEIPT#{receipt_id}',
        'SK': f'USER#{user_id}',
        'GSI1PK': f'USER#{user_id}',
        'GSI1SK': f'RECEIPT#{receipt_id}',
        'user_type': 'authenticated',
        'display_name': display_name,
        'email': email,
        'added_by': added_by_user_id,
        'added_at': datetime.now().isoformat()
    }
    
    table.put_item(
        Item=member_record,
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )
    
    return member_record

def add_placeholder_user_to_receipt(receipt_id, display_name, added_by_user_id):
    """
    Add a placeholder user to a receipt
    
    Args:
        receipt_id: ID of the receipt
        display_name: Display name for the placeholder user
        added_by_user_id: User ID of who added this user
        
    Returns:
        dict: The created member record with placeholder_id
    """
    table = dynamodb.Table(get_table_name())
    
    placeholder_id = str(uuid.uuid4())
    
    member_record = {
        'PK': f'RECEIPT#{receipt_id}',
        'SK': f'USER#{placeholder_id}',
        'GSI1PK': f'USER#{placeholder_id}',
        'GSI1SK': f'RECEIPT#{receipt_id}',
        'user_type': 'placeholder',
        'display_name': display_name,
        'placeholder_id': placeholder_id,
        'added_by': added_by_user_id,
        'added_at': datetime.now().isoformat()
    }
    
    table.put_item(
        Item=member_record,
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )
    
    return member_record

def get_receipt_members(receipt_id):
    """
    Get all users (authenticated and placeholder) on a receipt
    
    Args:
        receipt_id: ID of the receipt
        
    Returns:
        list: List of member records
    """
    table = dynamodb.Table(get_table_name())
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'RECEIPT#{receipt_id}')
    )
    
    return response.get('Items', [])

def get_user_receipts(user_id):
    """
    Get all receipts a user is on (both authenticated and placeholder users)
    
    Args:
        user_id: User ID (auth0|abc123 or placeholder UUID)
        
    Returns:
        list: List of receipt memberships
    """
    table = dynamodb.Table(get_table_name())
    
    response = table.query(
        IndexName='GSI1',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(f'USER#{user_id}')
    )
    
    return response.get('Items', [])

def claim_placeholder_user(placeholder_id, auth_user_id, display_name, email):
    """
    Claim a placeholder user by converting it to an authenticated user
    
    Args:
        placeholder_id: UUID of the placeholder user
        auth_user_id: Auth0 user ID
        display_name: User's display name
        email: User's email address
        
    Returns:
        list: Updated member records
    """
    table = dynamodb.Table(get_table_name())
    
    # First, get all receipts the placeholder user is on
    placeholder_receipts = get_user_receipts(placeholder_id)
    
    updated_records = []
    
    for receipt_membership in placeholder_receipts:
        receipt_id = receipt_membership['GSI1SK'].replace('RECEIPT#', '')
        
        # Delete the old placeholder record
        table.delete_item(
            Key={
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'USER#{placeholder_id}'
            }
        )
        
        # Create new authenticated user record
        new_record = {
            'PK': f'RECEIPT#{receipt_id}',
            'SK': f'USER#{auth_user_id}',
            'GSI1PK': f'USER#{auth_user_id}',
            'GSI1SK': f'RECEIPT#{receipt_id}',
            'user_type': 'authenticated',
            'display_name': display_name,
            'email': email,
            'added_by': receipt_membership.get('added_by'),
            'added_at': receipt_membership.get('added_at'),
            'claimed_at': datetime.now().isoformat(),
            'claimed_from_placeholder': placeholder_id
        }
        
        table.put_item(
            Item=new_record,
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )
        
        updated_records.append(new_record)
    
    return updated_records

def remove_user_from_receipt(receipt_id, user_id):
    """
    Remove a user from a receipt
    
    Args:
        receipt_id: ID of the receipt
        user_id: User ID to remove
        
    Returns:
        bool: True if user was removed, False if not found
    """
    table = dynamodb.Table(get_table_name())
    
    try:
        table.delete_item(
            Key={
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'USER#{user_id}'
            },
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)'
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False

def update_user_display_name(receipt_id, user_id, new_display_name):
    """
    Update a user's display name on a specific receipt
    
    Args:
        receipt_id: ID of the receipt
        user_id: User ID to update
        new_display_name: New display name
        
    Returns:
        dict: Updated member record
    """
    table = dynamodb.Table(get_table_name())
    
    response = table.update_item(
        Key={
            'PK': f'RECEIPT#{receipt_id}',
            'SK': f'USER#{user_id}'
        },
        UpdateExpression='SET display_name = :name, updated_at = :timestamp',
        ExpressionAttributeValues={
            ':name': new_display_name,
            ':timestamp': datetime.now().isoformat()
        },
        ReturnValues='ALL_NEW'
    )
    
    return response.get('Attributes', {})