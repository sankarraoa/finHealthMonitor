#!/usr/bin/env python3
"""
Script to convert existing URL-based user avatars to base64 data URLs.

This script:
1. Finds all users with URL-based image_url (starts with http:// or https://)
2. Downloads the image
3. Resizes/optimizes it (200x200px, max 50KB)
4. Converts to base64 data URL
5. Updates the database

Run this script once to migrate existing avatars.
"""

import sys
import os
import base64
import requests
from io import BytesIO
from typing import Optional
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.party import Person
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Image optimization settings
MAX_SIZE = (200, 200)  # Maximum dimensions
MAX_FILE_SIZE = 50 * 1024  # 50KB max for base64
QUALITY = 85  # JPEG quality


def optimize_image(image_data: bytes) -> Optional[bytes]:
    """
    Optimize image: resize to max 200x200 and compress.
    Returns optimized image bytes or None if optimization fails.
    """
    try:
        # Open image
        img = Image.open(BytesIO(image_data))
        
        # Convert RGBA to RGB if needed (for JPEG)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Resize maintaining aspect ratio
        img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
        
        # Save to bytes with optimization
        output = BytesIO()
        img.save(output, format='JPEG', quality=QUALITY, optimize=True)
        optimized_data = output.getvalue()
        
        # Check size
        if len(optimized_data) > MAX_FILE_SIZE:
            # Try lower quality
            output = BytesIO()
            quality = 70
            while quality >= 50 and len(output.getvalue()) > MAX_FILE_SIZE:
                output = BytesIO()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                quality -= 10
            optimized_data = output.getvalue()
        
        logger.info(f"Optimized image: {len(image_data)} bytes -> {len(optimized_data)} bytes")
        return optimized_data
        
    except Exception as e:
        logger.error(f"Error optimizing image: {str(e)}")
        return None


def url_to_base64(image_url: str) -> Optional[str]:
    """
    Download image from URL and convert to base64 data URL.
    Returns base64 data URL string or None if conversion fails.
    """
    try:
        logger.info(f"Downloading image from: {image_url}")
        
        # Download image
        response = requests.get(image_url, timeout=10, stream=True)
        response.raise_for_status()
        
        # Read image data
        image_data = response.content
        
        # Optimize image
        optimized_data = optimize_image(image_data)
        if not optimized_data:
            logger.warning(f"Failed to optimize image from {image_url}")
            return None
        
        # Convert to base64
        base64_data = base64.b64encode(optimized_data).decode('utf-8')
        
        # Create data URL
        # Detect format from original URL or use JPEG as default
        if '.png' in image_url.lower():
            mime_type = 'image/png'
        elif '.gif' in image_url.lower():
            mime_type = 'image/gif'
        elif '.webp' in image_url.lower():
            mime_type = 'image/webp'
        else:
            mime_type = 'image/jpeg'  # Default to JPEG after optimization
        
        data_url = f"data:{mime_type};base64,{base64_data}"
        
        logger.info(f"Converted to base64: {len(data_url)} characters")
        return data_url
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading image from {image_url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error converting image to base64: {str(e)}")
        return None


def is_url(image_url: str) -> bool:
    """Check if image_url is a URL (starts with http:// or https://)."""
    return image_url and (image_url.startswith('http://') or image_url.startswith('https://'))


def convert_avatars_to_base64():
    """Main function to convert all URL-based avatars to base64."""
    db = SessionLocal()
    
    try:
        # Find all users with URL-based image_url
        users = db.query(Person).filter(
            Person.image_url.isnot(None),
            Person.image_url != ''
        ).all()
        
        logger.info(f"Found {len(users)} users with image_url")
        
        converted_count = 0
        skipped_count = 0
        error_count = 0
        
        for user in users:
            if not is_url(user.image_url):
                # Already base64 or invalid, skip
                skipped_count += 1
                continue
            
            logger.info(f"Processing user: {user.email} ({user.full_name})")
            
            # Convert URL to base64
            base64_data_url = url_to_base64(user.image_url)
            
            if base64_data_url:
                # Update database
                user.image_url = base64_data_url
                db.commit()
                converted_count += 1
                logger.info(f"✅ Converted avatar for {user.email}")
            else:
                error_count += 1
                logger.warning(f"⚠️ Failed to convert avatar for {user.email}")
        
        logger.info("=" * 60)
        logger.info(f"Conversion complete!")
        logger.info(f"  ✅ Converted: {converted_count}")
        logger.info(f"  ⏭️  Skipped (already base64): {skipped_count}")
        logger.info(f"  ❌ Errors: {error_count}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Avatar URL to Base64 Conversion Script")
    print("=" * 60)
    print()
    print("This script will:")
    print("  1. Find all users with URL-based image_url")
    print("  2. Download and optimize images (200x200px, max 50KB)")
    print("  3. Convert to base64 data URLs")
    print("  4. Update the database")
    print()
    
    response = input("Continue? (yes/no): ")
    if response.lower() not in ('yes', 'y'):
        print("Cancelled.")
        sys.exit(0)
    
    print()
    convert_avatars_to_base64()
