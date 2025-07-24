import os
if not os.getenv('_INTERNAL_USE_ONLY'):
    raise RuntimeError("Unauthorized usage detected")
