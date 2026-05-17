from django import template
from Movies.utils import get_youtube_embed_url

register = template.Library()

@register.simple_tag
def youtube_embed_url(url):
    return get_youtube_embed_url(url) or ''