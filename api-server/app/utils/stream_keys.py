import random
import string

def generate_stream_key(length: int = 8) -> str:
    """Generate a random stream key of specified length."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def validate_stream_key(stream_key: str) -> bool:
    """Validate that a stream key meets our requirements."""
    if not stream_key or len(stream_key) != 8:
        return False
    return all(c in string.ascii_letters + string.digits for c in stream_key) 