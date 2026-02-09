# Scripts

Utility scripts for FinHealthMonitor.

## convert_avatars_to_base64.py

Converts existing URL-based user avatars to base64 data URLs stored in the database.

### Usage

```bash
# Make sure you're in the project root
cd /path/to/finHealthMonitor

# Run the script
python scripts/convert_avatars_to_base64.py
```

### What it does

1. Finds all users with URL-based `image_url` (starts with `http://` or `https://`)
2. Downloads the image from the URL
3. Optimizes the image:
   - Resizes to maximum 200x200px (maintains aspect ratio)
   - Compresses to JPEG format
   - Limits file size to 50KB
4. Converts to base64 data URL
5. Updates the database

### Requirements

- `Pillow` - For image processing
- `requests` - For downloading images
- Database connection configured

### Example

```bash
$ python scripts/convert_avatars_to_base64.py

============================================================
Avatar URL to Base64 Conversion Script
============================================================

This script will:
  1. Find all users with URL-based image_url
  2. Download and optimize images (200x200px, max 50KB)
  3. Convert to base64 data URLs
  4. Update the database

Continue? (yes/no): yes

INFO: Found 5 users with image_url
INFO: Processing user: john@example.com (John Doe)
INFO: Downloading image from: https://ui-avatars.com/api/?name=John+Doe&size=128
INFO: Optimized image: 15234 bytes -> 8234 bytes
INFO: Converted to base64: 10987 characters
INFO: ✅ Converted avatar for john@example.com
...
============================================================
Conversion complete!
  ✅ Converted: 5
  ⏭️  Skipped (already base64): 0
  ❌ Errors: 0
============================================================
```

## optimize_avatar_upload.py

Helper functions for optimizing avatar images before base64 encoding.

Can be imported and used in your application code:

```python
from scripts.optimize_avatar_upload import optimize_and_encode_image

# Optimize uploaded image
with open('avatar.jpg', 'rb') as f:
    image_data = f.read()
    
base64_data_url = optimize_and_encode_image(image_data)
# Returns: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
```
