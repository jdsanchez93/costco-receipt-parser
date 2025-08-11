import json
import urllib.parse
import boto3
from single_table import (
    write_receipt_items, 
    store_receipt_geometry,
    add_authenticated_user_to_receipt,
    create_pending_user_receipt
)
from textract_ocr import get_receipt_data_from_s3

# import requests

s3 = boto3.client('s3')

def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        S3 event notification

        Event doc: https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

        Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """

    #print("Received event: " + json.dumps(event, indent=2))

    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    try:
        receipt_items, special_fields = get_receipt_data_from_s3(bucket, key)

        # Extract user_id and receipt_id from key (expected format: uploads/{user_id}/{receipt_id}.jpg)
        parts = key.split('/')
        if len(parts) >= 3 and parts[0] == 'uploads':
            user_id = parts[1]
            receipt_id = parts[2].rsplit('.', 1)[0]  # strip file extension
        else:
            raise ValueError(f"Unexpected S3 key format: {key}")

        write_receipt_items(
            receipt_id=receipt_id,
            items=receipt_items,
            assigned_users=[user_id]
        )

        # Store geometry data for highlighting
        store_receipt_geometry(receipt_id=receipt_id, special_fields=special_fields)

        # Add the user as the owner of this receipt
        # Note: In a real implementation, you'd extract display_name and email from the JWT token
        # For now, we'll use placeholder values
        add_authenticated_user_to_receipt(
            receipt_id=receipt_id,
            user_id=user_id,
            display_name="Receipt Owner",  # Should be extracted from JWT
            email="user@example.com",      # Should be extracted from JWT
            added_by_user_id=user_id,      # User added themselves
            role="owner"                   # Mark as owner since they uploaded it
        )

        create_pending_user_receipt(user_id=user_id, receipt_id=receipt_id)
        
        # Log detected special fields for debugging
        if special_fields:
            print(f"Detected special fields for receipt {receipt_id}: {list(special_fields.keys())}")

    except Exception as e:
        print('Error:')
        print(e)
        raise e
