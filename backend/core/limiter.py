"""
MODULE: Shared rate limiter instance using slowapi.

@level-one-validation: Simple rate limiter singleton initialized with remote IP key function. Tested in test_api.py and test_security.py.

#Scope-Of-Improvement: Use Redis storage backend for slowapi to share rate limit counts across multiple API worker nodes.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# @risk-area: In-memory rate limiting tracks limits per process; multi-worker deployments require Redis storage backend to enforce global rate limits.
# #Business-Intent: Protects backend LLM services from denial-of-service and API cost abuse by enforcing IP-based rate limits.
limiter = Limiter(key_func=get_remote_address)
