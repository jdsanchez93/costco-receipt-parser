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
4. **Data Storage**: Single DynamoDB table with multiple entity types:
   - Receipt Items: `PK=RECEIPT#{receipt_id}`, `SK=ITEM#{item_id}`
   - Receipt Members: `PK=RECEIPT#{receipt_id}`, `SK=USER#{user_id}`
   - User Receipts: `PK=USER#{user_id}`, `SK=RECEIPT#{receipt_id}`
   - Share Tokens: `PK=SHARE#{token}`, `SK=RECEIPT#{receipt_id}`
   - Receipt Geometry: `PK=RECEIPT#{receipt_id}`, `SK=GEOMETRY#{field}#{type}`

### S3 Key Structure
Expected format: `uploads/{user_id}/{receipt_id}.jpg`

### Core Components

- `hello_world/app.py`: Main Lambda handler for S3 events
- `hello_world/upload_url.py`: Lambda handler for generating presigned S3 upload URLs
- `hello_world/download_url.py`: Lambda handler for generating presigned S3 download URLs
- `hello_world/textract_ocr.py`: OCR processing and receipt parsing logic with geometry detection
- `hello_world/single_table.py`: All DynamoDB operations using single-table design pattern
- `hello_world/dynamodb.py`: Legacy wrapper for backward compatibility
- `hello_world/receipt_members.py`: Legacy wrapper for backward compatibility
- `hello_world/receipt_shares.py`: Legacy wrapper for backward compatibility
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

## Single Table Design

The application uses a single DynamoDB table with multiple entity types and access patterns optimized through Global Secondary Indexes (GSIs). This design keeps you within the AWS Free Tier even with multiple deployments.

### Table Structure:
- **Main Table**: `{stack-name}-main`
- **GSI1**: For user-based queries
- **GSI2**: For receipt share lookups
- **TTL**: Enabled on `expires_at` attribute for automatic cleanup

### Key Access Patterns:
1. **Get all items for a receipt**: Query `PK = RECEIPT#{receipt_id}`, `SK begins_with ITEM#`
2. **Get all members of a receipt**: Query `PK = RECEIPT#{receipt_id}`, `SK begins_with USER#`
3. **Get all receipts for a user**: GSI1 Query `GSI1PK = USER#{user_id}`
4. **Get receipt from share token**: Query `PK = SHARE#{share_token}`
5. **Get all shares for a receipt**: GSI2 Query `GSI2PK = RECEIPT#{receipt_id}`, `GSI2SK begins_with SHARE#`
6. **Get geometry for highlighting**: Query `PK = RECEIPT#{receipt_id}`, `SK begins_with GEOMETRY#`

### Entity Schemas:
```
# Receipt Item
{
  "PK": "RECEIPT#12345",
  "SK": "ITEM#001",
  "entity_type": "RECEIPT_ITEM",
  "item_number": "123",
  "item_name": "Bananas",
  "price": 3.99,
  "discount": 0.50,
  "assigned_users": ["auth0|user123"]
}

# Receipt Member (Authenticated User)
{
  "PK": "RECEIPT#12345",
  "SK": "USER#auth0|abc123",
  "GSI1PK": "USER#auth0|abc123",
  "GSI1SK": "RECEIPT#12345",
  "entity_type": "RECEIPT_MEMBER",
  "user_type": "authenticated",
  "display_name": "John Doe",
  "email": "john@example.com",
  "added_by": "auth0|owner123"
}

# Receipt Member (Placeholder User)
{
  "PK": "RECEIPT#12345",
  "SK": "USER#uuid456",
  "GSI1PK": "USER#uuid456",
  "GSI1SK": "RECEIPT#12345",
  "entity_type": "RECEIPT_MEMBER",
  "user_type": "placeholder",
  "display_name": "Sarah",
  "placeholder_id": "uuid456",
  "added_by": "auth0|owner123"
}

# User-Receipt Relationship
{
  "PK": "USER#auth0|abc123",
  "SK": "RECEIPT#12345",
  "entity_type": "USER_RECEIPT",
  "status": "active"
}

# Share Token
{
  "PK": "SHARE#token789",
  "SK": "RECEIPT#12345",
  "GSI2PK": "RECEIPT#12345",
  "GSI2SK": "SHARE#token789",
  "entity_type": "RECEIPT_SHARE",
  "owner_user_id": "auth0|owner123",
  "expires_at": 1708176000,  // TTL timestamp
  "is_active": true,
  "current_uses": 0
}

# Receipt Geometry
{
  "PK": "RECEIPT#12345",
  "SK": "GEOMETRY#SUBTOTAL#VALUE",
  "entity_type": "RECEIPT_GEOMETRY",
  "field_name": "subtotal",
  "field_type": "value",
  "text": "15.99",
  "bounding_box": {...},
  "polygon": [...]
}
```

### Use Cases:
1. **Add Authenticated User**: Add existing Auth0 user to receipt
2. **Add Placeholder User**: Add "John Doe" to receipt before John has an account
3. **Claim Placeholder**: John signs up and claims his placeholder user (converts to authenticated)
4. **Share Receipt**: Generate time-limited share token for receipt access
5. **Access via Share**: Use share token to view receipt without being a member

### Key Functions:

**Core Functions (`single_table.py`)**:

*Receipt Items:*
- `write_receipt_items()`: Store receipt items after OCR processing
- `get_receipt_items()`: Get all items for a receipt

*Receipt Members:*
- `add_authenticated_user_to_receipt()`: Add Auth0 user to receipt
- `add_placeholder_user_to_receipt()`: Add placeholder user to receipt
- `get_receipt_members()`: Get all users on a receipt
- `get_user_receipts()`: Get all receipts for a user
- `claim_placeholder_user()`: Convert placeholder to authenticated user

*Receipt Shares:*
- `create_receipt_share()`: Generate share token with TTL expiration
- `get_receipt_from_share_token()`: Validate and retrieve receipt from share token
- `get_active_shares_for_receipt()`: List all active shares for a receipt
- `increment_share_usage()`: Track share token usage
- `deactivate_share()`: Manually deactivate a share token

*Receipt Geometry:*
- `store_receipt_geometry()`: Store geometry data for highlighting
- `get_receipt_geometry()`: Retrieve geometry data for a receipt

### Cost Optimization:
- **Single Table**: Only 1 table + 2 GSIs per deployment (3 RCU + 3 WCU total)
- **Multiple Deployments**: Dev (3) + Prod (3) = 6 total units, well under 25 RCU/WCU free tier
- **TTL**: Automatic cleanup of expired shares without consuming capacity

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
// Query the main table for geometry data
const geometryData = await queryDynamoDB({
  TableName: `${stackName}-main`,
  KeyConditionExpression: 'PK = :pk AND begins_with(SK, :sk)',
  ExpressionAttributeValues: {
    ':pk': `RECEIPT#${receiptId}`,
    ':sk': 'GEOMETRY#'
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
- **Single DynamoDB table**: MainTable with 2 GSIs, using provisioned throughput (1 RCU/WCU each to stay in free tier)
- **IAM roles and policies**: Least-privilege access for all functions