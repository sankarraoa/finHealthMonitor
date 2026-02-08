-- Add image URLs for all users based on their names
-- Using UI Avatars service: https://ui-avatars.com/
-- Format: https://ui-avatars.com/api/?name=FirstName+LastName&size=128&background=random

UPDATE persons
SET image_url = CASE
    WHEN first_name IS NOT NULL AND last_name IS NOT NULL THEN
        'https://ui-avatars.com/api/?name=' || 
        REPLACE(first_name || '+' || last_name, ' ', '+') || 
        '&size=128&background=random&color=fff&bold=true'
    WHEN first_name IS NOT NULL THEN
        'https://ui-avatars.com/api/?name=' || 
        REPLACE(first_name, ' ', '+') || 
        '&size=128&background=random&color=fff&bold=true'
    WHEN last_name IS NOT NULL THEN
        'https://ui-avatars.com/api/?name=' || 
        REPLACE(last_name, ' ', '+') || 
        '&size=128&background=random&color=fff&bold=true'
    ELSE
        'https://ui-avatars.com/api/?name=User&size=128&background=random&color=fff&bold=true'
END
WHERE image_url IS NULL OR image_url = '';

-- Verify the updates
SELECT id, email, first_name, last_name, image_url 
FROM persons 
ORDER BY email;
