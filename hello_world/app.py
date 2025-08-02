import json
import urllib.parse
import boto3
from dynamodb import create_pending_user_receipt, write_receipt_items_to_dynamodb
from textract_ocr import get_receipt_items_from_s3

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
        receipt_items = get_receipt_items_from_s3(bucket, key)

        write_receipt_items_to_dynamodb(
            receipt_id=key,
            items=receipt_items,
            assigned_users=[]  # Example user IDs, replace with actual logic
        )

        create_pending_user_receipt(user_id='me', receipt_id=key)

    except Exception as e:
        print('Error:')
        print(e)
        raise e
