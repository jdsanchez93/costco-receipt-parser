from decimal import Decimal
import boto3

dynamodb = boto3.resource('dynamodb')

# Function to write receipt items to DynamoDB for each assigned user
def write_receipt_items_to_dynamodb(receipt_id, items, assigned_users):
    table_name = 'ReceiptItems'  # Change this to your actual table name
    table = dynamodb.Table(table_name)
    converted_items = convert_floats(items)

    for item in items:
        for user_id in assigned_users:
            pk = f"USER#{user_id}"
            sk = f"RECEIPT#{receipt_id}|ITEM#{converted_items['item_number']}"
            # sk = f"RECEIPT#{receipt_id}"
            table.put_item(
                Item=convert_floats({
                    'PK': pk,
                    'SK': sk,
                    'item_name': converted_items['item'],
                    'price': converted_items['price'],
                    'discount': converted_items['discount'],
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