"""Frontend configuration and constants."""

import os

# API Configuration
# Internal URL — server-side Python requests.get() calls inside the container network.
# In Docker Compose: http://backend:8000/api/v1
# In Fargate: ECS service-discovery URL or internal ALB
API_BASE_URL = os.environ.get("REACT_APP_API_URL", "http://localhost:8000/api/v1")

# Public URL — embedded in iframe HTML/JS and fetched by the user's browser.
# In Docker Compose: http://localhost:8000/api/v1 (backend port exposed on the host)
# In Fargate: public ALB / CloudFront URL
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", API_BASE_URL)

API_TIMEOUT = int(os.environ.get("API_TIMEOUT", "60"))

# UI Configuration
MAP_CENTER = [20, 0]
MAP_INITIAL_ZOOM = 2
MAP_MAX_ZOOM = 19

# Feature flags
DEBUG_LOGGING = os.environ.get("DEBUG_LOGGING", "false").lower() == "true"
