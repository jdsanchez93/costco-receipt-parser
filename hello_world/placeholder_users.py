from datetime import datetime
from decimal import Decimal
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
placeholder_table = dynamodb.Table('PlaceholderUsers')

def create_placeholder_user(name, created_by_auth_user_id, receipt_id=None):
    """
    Create a new placeholder user
    
    Args:
        name: Display name for the placeholder user
        created_by_auth_user_id: ID of authenticated user who created this placeholder
        receipt_id: Optional receipt ID if this placeholder is created for a specific receipt
        
    Returns:
        dict: Created placeholder user data including placeholder_id
    """
    placeholder_id = str(uuid.uuid4())
    
    placeholder_user = {
        'PK': f'PLACEHOLDER#{placeholder_id}',
        'SK': 'METADATA',
        'placeholder_id': placeholder_id,
        'name': name,
        'status': 'unclaimed',
        'created_by': created_by_auth_user_id,
        'created_at': datetime.now().isoformat(),
        'claimed_by': None,
        'claimed_at': None,
        # GSI1 for lookups by authenticated user
        'GSI1PK': f'CREATOR#{created_by_auth_user_id}',
        'GSI1SK': f'PLACEHOLDER#{placeholder_id}'
    }
    
    if receipt_id:
        placeholder_user['initial_receipt_id'] = receipt_id
    
    placeholder_table.put_item(Item=placeholder_user)
    
    return placeholder_user

def claim_placeholder_user(placeholder_id, auth_user_id):
    """
    Claim a placeholder user by an authenticated user
    
    Args:
        placeholder_id: ID of the placeholder user to claim
        auth_user_id: ID of the authenticated user claiming this placeholder
        
    Returns:
        bool: True if successfully claimed, False if already claimed
    """
    try:
        response = placeholder_table.update_item(
            Key={
                'PK': f'PLACEHOLDER#{placeholder_id}',
                'SK': 'METADATA'
            },
            UpdateExpression='SET #status = :claimed, claimed_by = :user_id, claimed_at = :timestamp',
            ConditionExpression='#status = :unclaimed',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':claimed': 'claimed',
                ':unclaimed': 'unclaimed',
                ':user_id': auth_user_id,
                ':timestamp': datetime.now().isoformat()
            },
            ReturnValues='ALL_NEW'
        )
        return response['Attributes']
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Already claimed
        return None

def get_placeholder_user(placeholder_id):
    """
    Get placeholder user by ID
    
    Args:
        placeholder_id: ID of the placeholder user
        
    Returns:
        dict or None: Placeholder user data if found
    """
    response = placeholder_table.get_item(
        Key={
            'PK': f'PLACEHOLDER#{placeholder_id}',
            'SK': 'METADATA'
        }
    )
    return response.get('Item')

def list_placeholders_by_creator(auth_user_id):
    """
    List all placeholder users created by a specific authenticated user
    
    Args:
        auth_user_id: ID of the authenticated user
        
    Returns:
        list: List of placeholder users created by this user
    """
    response = placeholder_table.query(
        IndexName='GSI1',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI1PK').eq(f'CREATOR#{auth_user_id}')
    )
    return response.get('Items', [])

def resolve_user_id(user_identifier):
    """
    Resolve a user identifier to either an authenticated user ID or placeholder ID
    
    Args:
        user_identifier: Could be auth user ID (auth0|...) or placeholder ID (uuid)
        
    Returns:
        tuple: (resolved_user_id, is_placeholder_user)
    """
    # Check if this looks like an Auth0 user ID
    if user_identifier.startswith('auth0|') or user_identifier.startswith('google-oauth2|'):
        return user_identifier, False
    
    # Otherwise treat as placeholder ID
    placeholder = get_placeholder_user(user_identifier)
    if placeholder:
        if placeholder['status'] == 'claimed':
            # Return the claimed authenticated user ID
            return placeholder['claimed_by'], False
        else:
            # Still unclaimed placeholder
            return user_identifier, True
    
    # Unknown user identifier
    return user_identifier, False

def convert_floats(obj):
    """Convert floats to Decimal for DynamoDB compatibility"""
    if isinstance(obj, list):
        return [convert_floats(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj