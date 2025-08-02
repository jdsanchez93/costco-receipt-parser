from decimal import Decimal
import boto3

dynamodb = boto3.resource('dynamodb')

def write_receipt_items_to_dynamodb(receipt_id, items, assigned_users):
    table_name = 'ReceiptItems'  # Update to your actual table name
    table = dynamodb.Table(table_name)

    for item in items:
        pk = f"RECEIPT#{receipt_id}"
        sk = f"ITEM#{item['item_number']}"
        table.put_item(
            Item=convert_floats({
                'PK': pk,
                'SK': sk,
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