import re

def get_youtube_embed_url(url):
    """
    Safely extracts YouTube video ID and returns secure embed URL.
    Prevents XSS by validating and sanitizing input.
    """
    if not url:
        return None
    
    pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    
    if match:
        video_id = match.group(1)
        # Return secure embed URL with security parameters
        return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1"
    
    return None