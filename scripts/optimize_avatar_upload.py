#!/usr/bin/env python3
"""
Helper function to optimize avatar images before base64 encoding.

This can be used in the backend to optimize images uploaded via the API.
"""

import base64
from io import BytesIO
from typing import Optional
from PIL import Image

# Image optimization settings
MAX_SIZE = (200, 200)  # Maximum dimensions
MAX_FILE_SIZE = 50 * 1024  # 50KB max for base64
QUALITY = 85  # JPEG quality


def optimize_and_encode_image(image_data: bytes, max_size: tuple = MAX_SIZE, max_bytes: int = MAX_FILE_SIZE, quality: int = QUALITY) -> Optional[str]:
    """
    Optimize image and convert to base64 data URL.
    
    Args:
        image_data: Raw image bytes
        max_size: Maximum dimensions (width, height)
        max_bytes: Maximum file size in bytes
        quality: JPEG quality (1-100)
    
    Returns:
        Base64 data URL string or None if optimization fails
    """
    try:
        # Open image
        img = Image.open(BytesIO(image_data))
        original_format = img.format or 'JPEG'
        
        # Convert RGBA to RGB if needed (for JPEG)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Resize maintaining aspect ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Determine output format (prefer JPEG for smaller size)
        output_format = 'JPEG'
        mime_type = 'image/jpeg'
        
        # Save to bytes with optimization
        output = BytesIO()
        img.save(output, format=output_format, quality=quality, optimize=True)
        optimized_data = output.getvalue()
        
        # If still too large, reduce quality
        if len(optimized_data) > max_bytes:
            quality = 70
            while quality >= 50 and len(optimized_data) > max_bytes:
                output = BytesIO()
                img.save(output, format=output_format, quality=quality, optimize=True)
                optimized_data = output.getvalue()
                quality -= 10
        
        # Convert to base64
        base64_data = base64.b64encode(optimized_data).decode('utf-8')
        
        # Create data URL
        data_url = f"data:{mime_type};base64,{base64_data}"
        
        return data_url
        
    except Exception as e:
        print(f"Error optimizing image: {str(e)}")
        return None


def decode_base64_image(data_url: str) -> Optional[bytes]:
    """
    Decode base64 data URL back to image bytes.
    
    Args:
        data_url: Base64 data URL (e.g., "data:image/jpeg;base64,...")
    
    Returns:
        Image bytes or None if decoding fails
    """
    try:
        # Extract base64 data
        if ',' in data_url:
            base64_data = data_url.split(',')[1]
        else:
            base64_data = data_url
        
        # Decode
        image_bytes = base64.b64decode(base64_data)
        return image_bytes
    except Exception as e:
        print(f"Error decoding base64 image: {str(e)}")
        return None
