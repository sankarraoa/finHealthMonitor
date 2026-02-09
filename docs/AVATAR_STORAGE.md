# Avatar Image Storage

User avatars are stored as **base64 data URLs** directly in the `persons.image_url` database column.

## Why Base64 in Database?

- ✅ Simple implementation (no external storage needed)
- ✅ No additional infrastructure costs
- ✅ Works well for small images (avatars are typically <50KB)
- ✅ Suitable for applications with moderate user counts (<1M users)
- ✅ No CDN or file storage service required

## Image Optimization

### Client-Side (Frontend)
- File size validation: Maximum 2MB before upload
- File type validation: Only image files accepted
- Automatic base64 encoding via `FileReader.readAsDataURL()`

### Server-Side (Migration Script)
The `scripts/convert_avatars_to_base64.py` script optimizes images when converting from URLs:
- Resizes to maximum 200x200px (maintains aspect ratio)
- Converts to JPEG format
- Compresses to maximum 50KB
- Uses high-quality compression (quality=85, reduced if needed)

## Database Schema

```sql
-- persons table
image_url TEXT NULL  -- Stores base64 data URL like "data:image/jpeg;base64,/9j/4AAQ..."
```

## Format

Base64 data URLs are stored in this format:
```
data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD...
```

Where:
- `data:` - Protocol identifier
- `image/jpeg` - MIME type (usually JPEG after optimization)
- `base64,` - Encoding type
- `/9j/4AAQ...` - Base64-encoded image data

## Migration: Converting URL-based Avatars

If you have existing users with URL-based avatars (e.g., from UI Avatars service), run the migration script:

```bash
python scripts/convert_avatars_to_base64.py
```

This script will:
1. Find all users with `http://` or `https://` URLs in `image_url`
2. Download and optimize the images
3. Convert to base64 data URLs
4. Update the database

## Usage in Frontend

The frontend already handles base64 images correctly:

```html
<!-- In base.html -->
{% if current_user and current_user.image_url %}
    <img src="{{ current_user.image_url }}" alt="Avatar" />
{% endif %}
```

Since `image_url` contains a complete data URL, it can be used directly in `<img src="">` tags.

## File Size Considerations

### Typical Sizes
- **Optimized avatar (200x200px JPEG)**: ~5-15KB
- **Base64 encoding overhead**: ~33% increase
- **Final base64 string**: ~7-20KB
- **Database storage**: ~7-20KB per user

### Example Calculation
- 1,000 users × 15KB average = ~15MB total
- 10,000 users × 15KB average = ~150MB total
- 100,000 users × 15KB average = ~1.5GB total

For applications with <1M users, this is perfectly manageable.

## Best Practices

1. **Always optimize before storing**: Use the migration script or optimization helper
2. **Validate file size**: Limit uploads to 2MB before base64 encoding
3. **Validate file type**: Only accept image files
4. **Use JPEG format**: Best compression for photos
5. **Resize images**: Keep avatars small (200x200px max)

## Future Migration Path

If you ever need to migrate to external storage (S3, Cloudinary, etc.):

1. Create a migration script that:
   - Reads base64 data URLs from database
   - Decodes base64 to image bytes
   - Uploads to external storage
   - Updates `image_url` with new URL

2. The frontend code doesn't need to change (it already handles URLs)

## Troubleshooting

### Issue: Images not displaying
- Check if `image_url` starts with `data:`
- Verify base64 data is valid
- Check browser console for errors

### Issue: Database size growing too fast
- Ensure images are optimized before storage
- Run the migration script to optimize existing images
- Consider migrating to external storage if >100K users

### Issue: Slow page loads
- Base64 images are embedded in HTML, increasing page size
- Consider lazy loading for user lists
- For large user lists, consider pagination
