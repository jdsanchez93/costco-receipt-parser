import json
import boto3
from botocore.exceptions import ClientError
import os

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Generate a presigned URL for downloading receipt images from S3
    
    JWT validation is handled by API Gateway JWT authorizer.
    User info is available in event['requestContext']['authorizer']['jwt']['claims']
    
    Path parameters:
    - receipt_id: The ID of the receipt to download
    
    Returns:
    {
        "download_url": "presigned S3 URL",
        "expires_in": 3600
    }
    """
    
    try:
        # Extract user_id from JWT claims provided by API Gateway authorizer
        jwt_claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        
        # Try different claim names for user ID (Auth0 typically uses 'sub')
        user_id = jwt_claims.get('sub') or jwt_claims.get('user_id') or jwt_claims.get('uid')
        
        if not user_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'No user identifier found in JWT claims'
                })
            }
        
        # Extract receipt_id from path parameters
        receipt_id = event.get('pathParameters', {}).get('receipt_id')
        
        if not receipt_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'receipt_id path parameter is required'
                })
            }
        
        # Get bucket name from environment variable
        bucket_name = os.environ.get('BUCKET_NAME')
        if not bucket_name:
            raise ValueError('BUCKET_NAME environment variable not set')
        
        # Create S3 key following the expected format: uploads/{user_id}/{receipt_id}.jpg
        s3_key = f"uploads/{user_id}/{receipt_id}.jpg"
        
        # Verify the object exists and belongs to the user (security check)
        try:
            s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                        'Access-Control-Allow-Methods': 'GET,OPTIONS'
                    },
                    'body': json.dumps({
                        'error': 'Receipt not found or access denied'
                    })
                }
            else:
                raise
        
        # Generate presigned URL for GET operation
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        # Log for debugging
        print(f"Generated download URL for user: {user_id}, receipt: {receipt_id}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'download_url': presigned_url,
                'receipt_id': receipt_id,
                'expires_in': 3600
            })
        }
        
    except ClientError as e:
        print(f'AWS Client Error: {e}')
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Failed to generate download URL'
            })
        }
    except Exception as e:
        print(f'Error: {e}')
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }