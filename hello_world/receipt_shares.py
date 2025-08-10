from datetime import datetime, timedelta
import boto3
import boto3.dynamodb.conditions
import secrets
import os

dynamodb = boto3.resource('dynamodb')

def get_table_name():
    """Get the table name based on stack name"""
    stack_name = os.environ.get('AWS_STACK_NAME', 'costco-receipt-parser')
    return f"{stack_name}-receipt-shares"

def generate_share_token():
    """Generate a secure random share token"""
    return secrets.token_urlsafe(32)

def create_receipt_share(receipt_id, owner_user_id, expires_in_days=30):
    """
    Create a share token for a receipt
    
    Args:
        receipt_id: ID of the receipt to share
        owner_user_id: User ID of the receipt owner
        expires_in_days: Number of days until the share expires (default 30)
        
    Returns:
        dict: The created share record
    """
    table = dynamodb.Table(get_table_name())
    
    share_token = generate_share_token()
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=expires_in_days)
    
    # Convert to Unix timestamp for DynamoDB TTL
    expires_at_timestamp = int(expires_at.timestamp())
    
    share_record = {
        'PK': f'SHARE#{share_token}',
        'SK': f'RECEIPT#{receipt_id}',
        'GSI1PK': f'RECEIPT#{receipt_id}',
        'GSI1SK': f'SHARE#{share_token}',
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
    """
    Get receipt information from a share token
    
    Args:
        share_token: The share token
        
    Returns:
        dict: Share record if valid and active, None otherwise
    """
    table = dynamodb.Table(get_table_name())
    
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
            
        # TTL will automatically handle expiration, but we can also check here
        expires_at = share_record.get('expires_at', 0)
        if expires_at < int(datetime.now().timestamp()):
            return None
            
        return share_record
        
    except Exception:
        return None

def get_active_shares_for_receipt(receipt_id):
    """
    Get all active shares for a receipt
    
    Args:
        receipt_id: ID of the receipt
        
    Returns:
        list: List of active share records
    """
    table = dynamodb.Table(get_table_name())
    
    response = table.query(
        IndexName='GSI1',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(f'RECEIPT#{receipt_id}') & 
                              boto3.dynamodb.conditions.Key('GSI1SK').begins_with('SHARE#')
    )
    
    # Filter out inactive shares (TTL will handle expired ones automatically)
    active_shares = [
        share for share in response.get('Items', [])
        if share.get('is_active', False)
    ]
    
    return active_shares

def increment_share_usage(share_token):
    """
    Increment the usage counter for a share token
    
    Args:
        share_token: The share token
        
    Returns:
        dict: Updated share record, or None if share not found/inactive
    """
    table = dynamodb.Table(get_table_name())
    
    try:
        response = table.update_item(
            Key={
                'PK': f'SHARE#{share_token}',
                'SK': f'RECEIPT#{share_token.split("#")[-1]}'  # Extract receipt_id if needed
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
    """
    Deactivate a share token
    
    Args:
        share_token: The share token to deactivate
        receipt_id: ID of the receipt (for the sort key)
        
    Returns:
        bool: True if deactivated successfully, False if not found
    """
    table = dynamodb.Table(get_table_name())
    
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

def delete_share(share_token, receipt_id):
    """
    Permanently delete a share token
    
    Args:
        share_token: The share token to delete
        receipt_id: ID of the receipt (for the sort key)
        
    Returns:
        bool: True if deleted successfully, False if not found
    """
    table = dynamodb.Table(get_table_name())
    
    try:
        table.delete_item(
            Key={
                'PK': f'SHARE#{share_token}',
                'SK': f'RECEIPT#{receipt_id}'
            },
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)'
        )
        return True
        
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False

def cleanup_expired_shares(receipt_id=None):
    """
    Manually cleanup expired shares (though TTL should handle this automatically)
    
    Args:
        receipt_id: Optional receipt ID to limit cleanup scope
        
    Returns:
        int: Number of shares cleaned up
    """
    table = dynamodb.Table(get_table_name())
    current_timestamp = int(datetime.now().timestamp())
    
    if receipt_id:
        # Clean up shares for a specific receipt
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(f'RECEIPT#{receipt_id}') & 
                                  boto3.dynamodb.conditions.Key('GSI1SK').begins_with('SHARE#'),
            FilterExpression=boto3.dynamodb.conditions.Attr('expires_at').lt(current_timestamp)
        )
    else:
        # This would require a scan, which is expensive. Better to rely on TTL.
        return 0
    
    expired_shares = response.get('Items', [])
    cleanup_count = 0
    
    for share in expired_shares:
        if delete_share(share['share_token'], share['receipt_id']):
            cleanup_count += 1
    
    return cleanup_count