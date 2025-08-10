# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style Guidelines

- Never use emojis anywhere in this repository - not in logs, comments, markdown files, or code
- Follow existing patterns and conventions when making changes

## Project Overview

This is a serverless AWS application that parses Costco receipt images using AWS Textract OCR. When receipt images are uploaded to an S3 bucket, a Lambda function processes them to extract itemized data and stores it in DynamoDB tables.

## Architecture

The application follows an event-driven serverless architecture:

1. **Upload API**: `UploadUrlFunction` generates presigned S3 URLs for frontend applications via `/upload-url` endpoint
2. **S3 Trigger**: Images uploaded to the `ReceiptImageBucket` trigger the Lambda function
3. **Lambda Processing**: `HelloWorldFunction` processes S3 events, extracts text via Textract, parses receipt items, and stores data
4. **Data Storage**: Five DynamoDB tables store the parsed data:
   - `ReceiptItems`: Individual items with PK=RECEIPT#{receipt_id}, SK=ITEM#{item_id}
   - `UserReceipts`: User-receipt associations with PK=USER#{user_id}, SK=RECEIPT#{receipt_id}
   - `ReceiptMembers`: Receipt membership with both authenticated and placeholder users
   - `ReceiptShares`: Share tokens for receipt access with TTL expiration
   - `ReceiptGeometry`: Stores bounding box and polygon data for highlighting special fields (subtotal, total, tax)

### S3 Key Structure
Expected format: `uploads/{user_id}/{receipt_id}.jpg`

### Core Components

- `hello_world/app.py`: Main Lambda handler for S3 events
- `hello_world/upload_url.py`: Lambda handler for generating presigned S3 upload URLs
- `hello_world/download_url.py`: Lambda handler for generating presigned S3 download URLs
- `hello_world/textract_ocr.py`: OCR processing and receipt parsing logic with geometry detection
- `hello_world/dynamodb.py`: DynamoDB operations for storing receipt data and geometry
- `hello_world/receipt_members.py`: Manages receipt membership for both authenticated and placeholder users
- `hello_world/receipt_shares.py`: Manages share tokens for receipt access
- `template.yaml`: SAM template defining AWS infrastructure

### API Endpoints

- `POST /upload-url`: Generate presigned URL for receipt upload
  - Authentication: JWT token in Authorization header (`Bearer <token>`)
  - User ID extracted from JWT claims (`sub`, `user_id`, or `uid`)
  - Optional body: `{"content_type": "image/jpeg"}` (supports JPEG, PNG, WebP, HEIC)
  - Response: `{"upload_url": "string", "receipt_id": "string", "expires_in": 3600, "content_type": "string"}`

- `GET /download-url/{receipt_id}`: Generate presigned URL for receipt download
  - Authentication: JWT token in Authorization header (`Bearer <token>`)
  - Path parameter: `receipt_id` - ID of the receipt to download
  - User can only access their own receipts (enforced by S3 key structure)
  - Response: `{"download_url": "string", "receipt_id": "string", "expires_in": 3600}`

Both endpoints have CORS enabled for frontend integration.

## Receipt Membership and Sharing System

The system supports both authenticated and placeholder users on receipts, with secure sharing via tokens:

### Key Access Patterns:
1. **Get all users on a receipt**: Query `PK = RECEIPT#{receipt_id}`
2. **Get all receipts a user is on**: GSI Query `GSI1PK = USER#{user_id}`
3. **Get receipt from share token**: Query `PK = SHARE#{share_token}`
4. **Get all active shares for a receipt**: GSI Query `GSI1PK = RECEIPT#{receipt_id}`, `GSI1SK begins_with SHARE#`

### ReceiptMembers Table Schema:
```
# Authenticated user
{
  "PK": "RECEIPT#12345",
  "SK": "USER#auth0|abc123",
  "GSI1PK": "USER#auth0|abc123",
  "GSI1SK": "RECEIPT#12345",
  "user_type": "authenticated",
  "display_name": "John Doe",
  "email": "john@example.com",
  "added_by": "auth0|owner123",
  "added_at": "2024-01-15T10:30:00Z"
}

# Placeholder user
{
  "PK": "RECEIPT#12345",
  "SK": "USER#placeholder_uuid456",
  "GSI1PK": "USER#placeholder_uuid456",
  "GSI1SK": "RECEIPT#12345",
  "user_type": "placeholder",
  "display_name": "Sarah",
  "placeholder_id": "placeholder_uuid456",
  "added_by": "auth0|owner123",
  "added_at": "2024-01-15T10:32:00Z"
}
```

### ReceiptShares Table Schema:
```
{
  "PK": "SHARE#share_token_789",
  "SK": "RECEIPT#12345",
  "GSI1PK": "RECEIPT#12345",
  "GSI1SK": "SHARE#share_token_789",
  "receipt_id": "12345",
  "owner_user_id": "auth0|owner123",
  "share_token": "share_token_789",
  "created_at": "2024-01-15T10:00:00Z",
  "expires_at": 1708176000,  // Unix timestamp for TTL
  "is_active": true,
  "current_uses": 0
}
```

### Use Cases:
1. **Add Authenticated User**: Add existing Auth0 user to receipt
2. **Add Placeholder User**: Add "John Doe" to receipt before John has an account
3. **Claim Placeholder**: John signs up and claims his placeholder user (converts to authenticated)
4. **Share Receipt**: Generate time-limited share token for receipt access
5. **Access via Share**: Use share token to view receipt without being a member

### Key Functions:

**Receipt Members (`receipt_members.py`)**:
- `add_authenticated_user_to_receipt()`: Add Auth0 user to receipt
- `add_placeholder_user_to_receipt()`: Add placeholder user to receipt
- `get_receipt_members()`: Get all users on a receipt
- `get_user_receipts()`: Get all receipts for a user
- `claim_placeholder_user()`: Convert placeholder to authenticated user
- `remove_user_from_receipt()`: Remove user from receipt

**Receipt Shares (`receipt_shares.py`)**:
- `create_receipt_share()`: Generate share token with TTL expiration
- `get_receipt_from_share_token()`: Validate and retrieve receipt from share token
- `get_active_shares_for_receipt()`: List all active shares for a receipt
- `increment_share_usage()`: Track share token usage
- `deactivate_share()`: Manually deactivate a share token

## Receipt Geometry Highlighting

The system automatically detects and stores geometry data for special receipt fields that can be highlighted in the frontend:

### Supported Fields:
- **Subtotal**: Detects "SUBTOTAL" text and captures geometry of both label and value
- **Total**: Detects "TOTAL" text and captures geometry of both label and value  
- **Tax**: Detects "TAX" text and captures geometry of both label and value

### ReceiptGeometry Table Schema:
```
PK: RECEIPT#{receipt_id}
SK: FIELD#{field_name}_{label|value}
receipt_id: receipt ID
field_name: "subtotal" | "total" | "tax"
field_type: "label" | "value"
text: detected text
confidence: Textract confidence score
bounding_box: {Width, Height, Left, Top} - normalized coordinates (0-1)
polygon: [{X, Y}, ...] - precise boundary points
```

### Frontend Usage Example:
```javascript
// Query ReceiptGeometry table directly via your frontend API
const geometryData = await queryDynamoDB({
  TableName: 'ReceiptGeometry',
  KeyConditionExpression: 'PK = :pk',
  ExpressionAttributeValues: {
    ':pk': `RECEIPT#${receiptId}`
  }
});

// Parse the geometry data
const fields = {};
geometryData.Items.forEach(item => {
  const fieldName = item.field_name;
  const fieldType = item.field_type;
  
  if (!fields[fieldName]) fields[fieldName] = {};
  
  fields[fieldName][fieldType] = {
    text: item.text,
    bounding_box: item.bounding_box,
    polygon: item.polygon
  };
});

// Highlight subtotal value
if (fields.subtotal) {
  const bbox = fields.subtotal.value.bounding_box;
  // Convert normalized coordinates to pixel coordinates
  const rect = {
    left: bbox.Left * imageWidth,
    top: bbox.Top * imageHeight,
    width: bbox.Width * imageWidth,
    height: bbox.Height * imageHeight
  };
  // Draw highlight box over receipt image
}
```

### Key Functions:
- `detect_special_fields()`: Identifies special fields and their geometry from Textract response
- `store_receipt_geometry()`: Saves geometry data to DynamoDB
- `get_receipt_geometry()`: Retrieves geometry data for a receipt

## Development Commands

### Building and Testing
```bash
# Build the application (uses container for consistent builds)
sam build --use-container

# Run unit tests
pip install -r tests/requirements.txt --user
python -m pytest tests/unit -v

# Run integration tests (requires deployed stack)
AWS_SAM_STACK_NAME="costco-receipt-parser" python -m pytest tests/integration -v

# Local testing
sam local invoke HelloWorldFunction --event events/event.json
sam local start-api
```

### Deployment
```bash
# First-time deployment
sam deploy --guided

# Subsequent deployments
sam deploy

# Deploy to dev environment
sam deploy --config-env dev

# Validate template
sam validate --lint
```

### Local Development
```bash
# Start API locally
sam local start-api

# Test upload URL endpoint locally (requires valid Auth0 JWT token)
curl -X POST http://localhost:3000/upload-url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-auth0-jwt-token>"

# Test download URL endpoint locally (requires valid Auth0 JWT token)
curl -X GET http://localhost:3000/download-url/your-receipt-id \
  -H "Authorization: Bearer <your-auth0-jwt-token>"

# View logs from deployed functions
sam logs -n HelloWorldFunction --stack-name "costco-receipt-parser" --tail
sam logs -n UploadUrlFunction --stack-name "costco-receipt-parser" --tail
sam logs -n DownloadUrlFunction --stack-name "costco-receipt-parser" --tail
```

### Testing Individual Components
```bash
# Test OCR parsing with local image (requires AWS profile)
cd hello_world
python textract_ocr.py /path/to/receipt.jpg your-aws-profile
python textract_ocr.py /path/to/receipt.jpg your-aws-profile --raw
```

## Key Implementation Details

### Receipt Parsing Logic
The OCR parsing in `textract_ocr.py` uses regex patterns to identify:
- Item lines: `^(?:E\s+)?(\d+)\s+(.+)` (optionally prefixed with 'E')
- Price lines: `^(-?\d+\.\d{2})(?:\s+\w+)?$`
- Discount lines: `^(?:E\s+)?\d+\s+/\s*(\d+)$` followed by negative amounts

### DynamoDB Schema
- Both tables use composite primary keys (PK/SK)
- Float values are converted to Decimal for DynamoDB compatibility
- Conditional writes prevent duplicate entries

### Error Handling
- S3 key format validation ensures proper user/receipt ID extraction
- DynamoDB condition expressions prevent overwrites
- Lambda errors are logged and re-raised to trigger retries
- JWT token validation prevents unauthorized access and ensures user identity

## Environment Configuration

### Stack Parameters
- `BucketName`: Name of the S3 bucket for receipt images
- `Auth0Domain`: Your Auth0 domain (e.g., your-domain.auth0.com)
- `Auth0Audience`: Auth0 audience/identifier for your API
- `AllowedOrigins`: Comma-separated list of allowed origins for CORS (both API Gateway and S3)

### SAM Configuration Profiles
- `default`: Standard deployment settings
- `dev`: Development environment with specific region/profile settings

### Auth0 JWT Authentication Setup

The upload URL endpoint uses API Gateway JWT authorizer for Auth0 integration:

```bash
sam deploy --parameter-overrides \
  Auth0Domain="your-domain.auth0.com" \
  Auth0Audience="your-api-identifier" \
  AllowedOrigins="http://localhost:3000,https://your-app.com"
```

**Auth0 Configuration Requirements:**
1. Create an API in your Auth0 dashboard
2. Set the audience/identifier for your API
3. Configure your frontend app to request tokens for this audience

**JWT Claims Processing:**
- API Gateway validates JWT signature and expiration automatically
- Lambda extracts user_id from JWT claims (in order of preference):
  - `sub` (standard JWT subject claim - Auth0 default)
  - `user_id` (custom claim)
  - `uid` (alternative custom claim)

## AWS Resources Created
- **ReceiptApi**: API Gateway with JWT authorizer for Auth0 integration
- **HelloWorldFunction**: Lambda function with S3, Textract, and DynamoDB permissions for receipt processing
- **UploadUrlFunction**: Lambda function with S3 PutObject permission for presigned upload URL generation
- **DownloadUrlFunction**: Lambda function with S3 GetObject permission for presigned download URL generation
- **S3 bucket**: Receipt storage with Lambda notification configuration and CORS for direct uploads
- **Five DynamoDB tables**: ReceiptItems, UserReceipts, ReceiptMembers, ReceiptShares, and ReceiptGeometry with provisioned throughput (1 RCU/WCU each to stay in free tier)
- **IAM roles and policies**: Least-privilege access for all functions