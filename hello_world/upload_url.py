import json
import boto3
import uuid
from botocore.exceptions import ClientError
import os

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Generate a presigned URL for uploading receipt images to S3
    
    JWT validation is handled by API Gateway JWT authorizer.
    User info is available in event['requestContext']['authorizer']['jwt']['claims']
    
    Optional request body:
    {
        "content_type": "image/jpeg" (optional, defaults to image/jpeg)
    }
    
    Returns:
    {
        "upload_url": "presigned S3 URL",
        "receipt_id": "generated receipt ID",
        "expires_in": 3600,
        "content_type": "image/jpeg"
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
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'No user identifier found in JWT claims'
                })
            }
        
        # Parse request body for optional content type
        content_type = 'image/jpeg'  # Default
        if event.get('body'):
            try:
                body = json.loads(event['body'])
                content_type = body.get('content_type', 'image/jpeg')
            except json.JSONDecodeError:
                # If body isn't valid JSON, just use default
                pass
        
        # Validate content type (security measure)
        allowed_content_types = [
            'image/jpeg',
            'image/jpg', 
            'image/png',
            'image/webp',
            'image/heic',
            'image/heif'
        ]
        
        if content_type not in allowed_content_types:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': f'Unsupported content type: {content_type}. Allowed types: {", ".join(allowed_content_types)}'
                })
            }
        
        # Generate unique receipt ID
        receipt_id = str(uuid.uuid4())
        
        # Get bucket name from environment variable
        bucket_name = os.environ.get('BUCKET_NAME')
        if not bucket_name:
            raise ValueError('BUCKET_NAME environment variable not set')
        
        # Create S3 key following the expected format: uploads/{user_id}/{receipt_id}.jpg
        s3_key = f"uploads/{user_id}/{receipt_id}.jpg"
        
        # Generate presigned URL for PUT operation
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'upload_url': presigned_url,
                'receipt_id': receipt_id,
                'expires_in': 3600,
                'content_type': content_type
            })
        }
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Invalid JSON in request body'
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
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Failed to generate upload URL'
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
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }

def options_handler(event, context):
    """Handle CORS preflight requests"""
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': ''
    }