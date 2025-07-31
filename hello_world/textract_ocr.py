import boto3
import argparse
import json
from pprint import pprint
import re

textract = boto3.client('textract')

def parse_items_from_lines(lines):
    items = []
    i = 0

    while i < len(lines) - 1:
        line1 = lines[i].strip()
        line2 = lines[i + 1].strip()

        # Match standard item line (optionally starting with 'E') followed by price/tax code line
        item_match = re.match(r'^(?:E\s+)?(\d+)\s+(.+)', line1)
        price_match = re.match(r'^(-?\d+\.\d{2})(?:\s+\w+)?$', line2)

        if item_match and price_match:
            item_number = item_match.group(1)
            item_name = item_match.group(2)
            price = float(price_match.group(1))
            tax_code = price_match.group(2) if len(price_match.groups()) > 1 else None

            # Add the item to the list
            items.append({
                "item_number": item_number,
                "item": item_name,
                "price": price,
                "tax_code": tax_code,
                "discount": 0.0
            })
            i += 2
            continue

        # Match discount line followed by negative price
        discount_match = re.match(r'^(?:E\s+)?\d+\s+/\s*(\d+)$', line1)
        discount_price_match = re.match(r'^(-?\d+\.\d{2})-?\w*$', line2)

        if discount_match and discount_price_match:
            related_item_number = discount_match.group(1)
            discount_amount = float(discount_price_match.group(1))

            # Try to apply the discount to the most recent matching item
            for item in reversed(items):
                if item['item_number'] == related_item_number:
                    item['discount'] += discount_amount
                    break
            i += 2
            continue

        # If neither pattern matches, move to the next line
        i += 1

    return items

def detect_text_local(file_path, profile_name):
    with open(file_path, 'rb') as doc:
        image_bytes = doc.read()

    session = boto3.Session(profile_name=profile_name)
    textract = session.client('textract')

    response = textract.detect_document_text(
        Document={'Bytes': image_bytes}
    )
    return response

def detect_text_s3(bucket, key):
    response = textract.detect_document_text(
        Document={'S3Object': {'Bucket': bucket, 'Name': key}}
    )
    return response

def extract_lines(response):
    return [
        block['Text']
        for block in response['Blocks']
        if block['BlockType'] == 'LINE'
    ]

def get_receipt_items_from_s3(bucket, key):
    response = detect_text_s3(bucket, key)
    lines = extract_lines(response)
    items = parse_items_from_lines(lines)
    return items

def main():
    parser = argparse.ArgumentParser(description='Run Amazon Textract OCR on a local image.')
    parser.add_argument('image_path', help='Path to the receipt image')
    parser.add_argument('profile_name', help='AWS profile name to use')
    parser.add_argument('--raw', action='store_true', help='Print full JSON response')

    args = parser.parse_args()

    print(f"Running Textract on: {args.image_path}")
    response = detect_text_local(args.image_path, args.profile_name)

    if args.raw:
        pprint(response)
    else:
        lines = extract_lines(response)
        print("\nDetected Text Lines:")
        for line in lines:
            print(line)

        print("\nParsed Items and Prices:")
        items = parse_items_from_lines(lines)
        total_price = sum(item['price'] - item['discount'] for item in items)
        for item in items:
            print(f"{item['item']:30} {item['price']:>6.2f}")
            if item['discount'] > 0:
                print(f"{"\tDiscount":22} -{item['discount']:>6.2f}")
        print(f"{'SubTotal':30} {total_price:>6.2f}")

if __name__ == '__main__':
    main()