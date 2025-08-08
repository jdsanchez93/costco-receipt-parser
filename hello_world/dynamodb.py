from datetime import datetime
from decimal import Decimal
import boto3
import boto3.dynamodb.conditions

dynamodb = boto3.resource('dynamodb')

def write_receipt_items_to_dynamodb(receipt_id, items, assigned_users):
    table_name = 'ReceiptItems'  # Update to your actual table name
    table = dynamodb.Table(table_name)

    for item in items:
        pk = f"RECEIPT#{receipt_id}"
        sk = f"ITEM#{item['item_id']}"
        table.put_item(
            Item=convert_floats({
                'PK': pk,
                'SK': sk,
                'item_number': item['item_number'],
                'item_name': item['item'],
                'price': item['price'],
                'discount': item['discount'],
                'receipt_id': receipt_id,
                'assigned_users': assigned_users
            }),
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )

def convert_floats(obj):
    if isinstance(obj, list):
        return [convert_floats(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj
    
def create_pending_user_receipt(user_id, receipt_id):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('UserReceipts')

    table.put_item(
        Item={
            'PK': f'USER#{user_id}',
            'SK': f'RECEIPT#{receipt_id}',
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        },
        ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
    )

def store_receipt_geometry(receipt_id, special_fields):
    """
    Store geometry data for special fields (subtotal, total, tax) that can be highlighted
    
    Args:
        receipt_id: ID of the receipt
        special_fields: Dictionary of detected special fields with geometry data
    """
    if not special_fields:
        return
        
    geometry_table = dynamodb.Table('ReceiptGeometry')
    
    for field_name, field_data in special_fields.items():
        # Store both label and value geometry for each field
        
        # Store label geometry
        geometry_table.put_item(
            Item=convert_floats({
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'FIELD#{field_name.upper()}_LABEL',
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
        geometry_table.put_item(
            Item=convert_floats({
                'PK': f'RECEIPT#{receipt_id}',
                'SK': f'FIELD#{field_name.upper()}_VALUE',
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
    """
    Retrieve geometry data for a receipt
    
    Args:
        receipt_id: ID of the receipt
        
    Returns:
        dict: Dictionary of field geometry data organized by field name
    """
    geometry_table = dynamodb.Table('ReceiptGeometry')
    
    response = geometry_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'RECEIPT#{receipt_id}')
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