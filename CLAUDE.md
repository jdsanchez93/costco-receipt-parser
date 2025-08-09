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
4. **Data Storage**: Four DynamoDB tables store the parsed data:
   - `ReceiptItems`: Individual items with PK=RECEIPT#{receipt_id}, SK=ITEM#{item_id}
   - `UserReceipts`: User-receipt associations with PK=USER#{user_id}, SK=RECEIPT#{receipt_id}
   - `PlaceholderUsers`: Manages placeholder users that can be claimed by authenticated users
   - `ReceiptGeometry`: Stores bounding box and polygon data for highlighting special fields (subtotal, total, tax)

### S3 Key Structure
Expected format: `uploads/{user_id}/{receipt_id}.jpg`

### Core Components

- `hello_world/app.py`: Main Lambda handler for S3 events
- `hello_world/upload_url.py`: Lambda handler for generating presigned S3 upload URLs
- `hello_world/download_url.py`: Lambda handler for generating presigned S3 download URLs
- `hello_world/textract_ocr.py`: OCR processing and receipt parsing logic with geometry detection
- `hello_world/dynamodb.py`: DynamoDB operations for storing receipt data and geometry
- `hello_world/placeholder_users.py`: Manages placeholder users and user identity resolution
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

## Placeholder User System

The system supports "placeholder users" that can later be claimed by authenticated users:

### PlaceholderUsers Table Schema:
```
PK: PLACEHOLDER#{placeholder_id}
SK: METADATA
placeholder_id: uuid
name: "Display name"
status: "unclaimed" | "claimed"
created_by: auth_user_id (who created this placeholder)
created_at: timestamp
claimed_by: auth_user_id (who claimed it) | null
claimed_at: timestamp | null
GSI1PK: CREATOR#{auth_user_id}
GSI1SK: PLACEHOLDER#{placeholder_id}
```

### Use Cases:
1. **Create Placeholder**: User adds "John Doe" to a receipt before John has an account
2. **Claim Placeholder**: John signs up and claims his placeholder user
3. **User Resolution**: System resolves placeholder IDs to authenticated users when available

### Key Functions:
- `create_placeholder_user()`: Create new placeholder user
- `claim_placeholder_user()`: Authenticated user claims a placeholder
- `resolve_user_id()`: Convert placeholder ID to auth user ID if claimed
- `list_placeholders_by_creator()`: List placeholders created by a user

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
- **Four DynamoDB tables**: ReceiptItems, UserReceipts, PlaceholderUsers, and ReceiptGeometry with provisioned throughput
- **IAM roles and policies**: Least-privilege access for all functions