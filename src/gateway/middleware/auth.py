"""Authentication and authorization middleware.

This module implements:
- Session token extraction from cookies and headers (Task 8)
- Session token validation (Task 9)
- User identity and permission resolution (Task 11)
- Authorization enforcement (Task 12)
- Token refresh mechanism (Task 13)
- Authentication and authorization middleware (Task 14)
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web

from gateway.core.config import GatewayConfig
from gateway.core.middleware import Middleware, MiddlewareHandler, RequestContext
from gateway.core.session_store import SessionData, SessionStore

logger = logging.getLogger(__name__)


class TokenExtractor:
    """Extracts session tokens from HTTP requests.

    Supports extracting tokens from:
    - Cookie header (primary method)
    - Authorization header (Bearer token)
    """

    def __init__(self, cookie_name: str = "session_token"):
        """Initialize token extractor.

        Args:
            cookie_name: Name of the session cookie
        """
        self.cookie_name = cookie_name

    def extract_from_cookie(self, request: web.Request) -> str | None:
        """Extract token from Cookie header.

        Args:
            request: aiohttp Request object

        Returns:
            Token string if found, None otherwise
        """
        try:
            # aiohttp provides cookies as a dict-like object
            return request.cookies.get(self.cookie_name)
        except Exception as e:
            logger.debug(f"Failed to extract token from cookie: {e}")
            return None

    def extract_from_header(self, request: web.Request) -> str | None:
        """Extract token from Authorization header.

        Supports "Bearer <token>" format.

        Args:
            request: aiohttp Request object

        Returns:
            Token string if found, None otherwise
        """
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:].strip()
            return None
        except Exception as e:
            logger.debug(f"Failed to extract token from header: {e}")
            return None

    def extract(self, request: web.Request) -> str | None:
        """Extract token from request (tries cookie first, then header).

        Args:
            request: aiohttp Request object

        Returns:
            Token string if found, None otherwise
        """
        # Try cookie first
        token = self.extract_from_cookie(request)
        if token:
            return token

        # Fallback to Authorization header
        return self.extract_from_header(request)


class TokenValidator:
    """Validates session tokens.

    Supports both:
    - Opaque tokens (validated via session store lookup)
    - Signed tokens (validated via HMAC signature)
    """

    def __init__(
        self,
        session_store: SessionStore,
        signing_secret: str | None = None,
        use_signed_tokens: bool = False,
    ):
        """Initialize token validator.

        Args:
            session_store: Session store for validation
            signing_secret: Secret for signing tokens (required if use_signed_tokens=True)
            use_signed_tokens: Whether to use signed tokens instead of opaque tokens
        """
        self.session_store = session_store
        self.signing_secret = signing_secret
        self.use_signed_tokens = use_signed_tokens

        if use_signed_tokens and not signing_secret:
            raise ValueError("signing_secret is required when use_signed_tokens=True")

    def _verify_signature(self, token: str) -> dict[str, Any] | None:
        """Verify signed token signature and extract payload.

        Token format: <payload_base64>.<signature_base64>

        Args:
            token: Signed token string

        Returns:
            Payload dict if signature is valid, None otherwise
        """
        try:
            if not self.signing_secret:
                logger.error("Cannot verify signature: signing_secret is None")
                return None

            parts = token.split(".")
            if len(parts) != 2:
                logger.debug("Invalid token format: expected 2 parts")
                return None

            payload_b64, signature_b64 = parts

            # Verify signature
            expected_signature = hmac.new(
                self.signing_secret.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature_b64, expected_signature):
                logger.warning("Token signature verification failed")
                return None

            # Decode payload
            import base64

            payload_json = base64.b64decode(payload_b64).decode()
            payload: dict[str, Any] = json.loads(payload_json)

            return payload

        except Exception as e:
            logger.warning(f"Failed to verify token signature: {e}")
            return None

    async def validate_opaque_token(self, token: str) -> SessionData | None:
        """Validate opaque token by looking it up in session store.

        Args:
            token: Opaque token (session ID)

        Returns:
            SessionData if valid, None otherwise
        """
        try:
            # Token is the session ID
            session_id = token

            # Look up session in store
            session_data = await self.session_store.get(session_id)

            if not session_data:
                logger.debug(f"Session {session_id} not found")
                return None

            # Check if revoked
            if session_data.revoked or await self.session_store.is_revoked(session_id):
                logger.info(f"Session {session_id} is revoked")
                return None

            # Check if expired
            if session_data.is_expired():
                logger.info(f"Session {session_id} is expired")
                await self.session_store.delete(session_id)
                return None

            return session_data

        except Exception as e:
            logger.error(f"Failed to validate opaque token: {e}")
            return None

    async def validate_signed_token(self, token: str) -> SessionData | None:
        """Validate signed token by verifying signature and checking claims.

        Args:
            token: Signed token string

        Returns:
            SessionData if valid, None otherwise
        """
        payload = self._verify_signature(token)

        if not payload:
            return None

        try:
            # Check expiration
            exp = payload.get("exp")
            if not exp:
                logger.warning("Token missing exp claim")
                return None

            exp_dt = datetime.fromisoformat(exp)
            if datetime.utcnow() >= exp_dt:
                logger.info("Token is expired")
                return None

            # Check not before (if present)
            nbf = payload.get("nbf")
            if nbf:
                nbf_dt = datetime.fromisoformat(nbf)
                if datetime.utcnow() < nbf_dt:
                    logger.info("Token not yet valid (nbf)")
                    return None

            # Check revocation (even for signed tokens)
            session_id = payload.get("session_id")
            if session_id and await self.session_store.is_revoked(session_id):
                logger.info(f"Signed token for session {session_id} is revoked")
                return None

            # Construct SessionData from payload
            session_data = SessionData(
                session_id=payload.get("session_id", ""),
                user_id=payload.get("user_id", ""),
                username=payload.get("username", ""),
                created_at=datetime.fromisoformat(
                    payload.get("iat", datetime.utcnow().isoformat())
                ),
                last_accessed_at=datetime.utcnow(),
                expires_at=exp_dt,
                revoked=False,
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                ip_address=payload.get("ip_address"),
                device_fingerprint=payload.get("device_fingerprint"),
                metadata=payload.get("metadata", {}),
            )

            return session_data

        except Exception as e:
            logger.error(f"Failed to validate signed token: {e}")
            return None

    async def validate(self, token: str) -> SessionData | None:
        """Validate token (dispatches to appropriate validator).

        Args:
            token: Token string

        Returns:
            SessionData if valid, None otherwise
        """
        if self.use_signed_tokens:
            return await self.validate_signed_token(token)
        else:
            return await self.validate_opaque_token(token)


class TokenRefresher:
    """Handles token refresh mechanism."""

    def __init__(
        self,
        session_store: SessionStore,
        refresh_threshold: int = 300,
        token_ttl: int = 3600,
        signing_secret: str | None = None,
        use_signed_tokens: bool = False,
    ):
        """Initialize token refresher.

        Args:
            session_store: Session store
            refresh_threshold: Refresh threshold in seconds (refresh if less than this remains)
            token_ttl: Token TTL in seconds
            signing_secret: Secret for signing tokens
            use_signed_tokens: Whether to use signed tokens
        """
        self.session_store = session_store
        self.refresh_threshold = refresh_threshold
        self.token_ttl = token_ttl
        self.signing_secret = signing_secret
        self.use_signed_tokens = use_signed_tokens

    def should_refresh(self, session_data: SessionData) -> bool:
        """Check if session should be refreshed.

        Args:
            session_data: Current session data

        Returns:
            True if session should be refreshed, False otherwise
        """
        time_until_expiry = (session_data.expires_at - datetime.utcnow()).total_seconds()
        return time_until_expiry < self.refresh_threshold

    async def refresh(self, session_data: SessionData) -> tuple[SessionData, str | None]:
        """Refresh session and generate new token if needed.

        Args:
            session_data: Current session data

        Returns:
            Tuple of (updated SessionData, new token or None)
        """
        if not self.should_refresh(session_data):
            return session_data, None

        try:
            # Update session expiration
            session_data.expires_at = datetime.utcnow() + timedelta(seconds=self.token_ttl)
            session_data.last_accessed_at = datetime.utcnow()

            # Update in store
            await self.session_store.update(session_data)

            # Generate new token if using opaque tokens
            if not self.use_signed_tokens:
                # For opaque tokens, session ID is the token
                new_token = session_data.session_id
            else:
                # For signed tokens, generate new signed token
                new_token = self._generate_signed_token(session_data)

            logger.info(f"Refreshed session {session_data.session_id}")
            return session_data, new_token

        except Exception as e:
            logger.error(f"Failed to refresh session: {e}")
            return session_data, None

    def _generate_signed_token(self, session_data: SessionData) -> str:
        """Generate signed token from session data.

        Args:
            session_data: Session data

        Returns:
            Signed token string
        """
        import base64

        if not self.signing_secret:
            raise RuntimeError("Cannot generate signed token: signing_secret is None")

        # Build payload
        payload = {
            "session_id": session_data.session_id,
            "user_id": session_data.user_id,
            "username": session_data.username,
            "iat": session_data.created_at.isoformat(),
            "exp": session_data.expires_at.isoformat(),
            "roles": session_data.roles,
            "permissions": session_data.permissions,
            "ip_address": session_data.ip_address,
            "device_fingerprint": session_data.device_fingerprint,
            "metadata": session_data.metadata,
        }

        # Encode payload
        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode()).decode()

        # Generate signature
        signature = hmac.new(
            self.signing_secret.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()

        # Combine into token
        return f"{payload_b64}.{signature}"


class Authorizer:
    """Enforces authorization policies."""

    def authorize(self, session_data: SessionData, required_roles: list[str]) -> bool:
        """Check if session has required roles for access.

        Args:
            session_data: Session data with user roles
            required_roles: List of required roles

        Returns:
            True if authorized, False otherwise
        """
        # If no roles required, allow access
        if not required_roles:
            return True

        # Check if user has any of the required roles
        user_roles = set(session_data.roles or [])
        required = set(required_roles)

        return bool(user_roles & required)


class AuthenticationMiddleware(Middleware):
    """Middleware for authentication and authorization.

    This middleware:
    1. Extracts session tokens from requests
    2. Validates tokens
    3. Resolves user identity and permissions
    4. Enforces authorization rules
    5. Handles token refresh
    """

    def __init__(
        self,
        config: GatewayConfig,
        session_store: SessionStore,
    ):
        """Initialize authentication middleware.

        Args:
            config: Gateway configuration
            session_store: Session store instance
        """
        super().__init__(config)
        self.session_store = session_store

        # Initialize components
        self.extractor = TokenExtractor(cookie_name=config.session.cookie_name)

        # Determine if using signed tokens
        use_signed_tokens = config.session.token_signing_secret is not None

        self.validator = TokenValidator(
            session_store=session_store,
            signing_secret=config.session.token_signing_secret,
            use_signed_tokens=use_signed_tokens,
        )

        self.refresher = (
            TokenRefresher(
                session_store=session_store,
                refresh_threshold=config.session.refresh_threshold,
                token_ttl=config.session.token_ttl,
                signing_secret=config.session.token_signing_secret,
                use_signed_tokens=use_signed_tokens,
            )
            if config.session.refresh_enabled
            else None
        )

        self.authorizer = Authorizer()

    async def process(
        self, request: web.Request, context: RequestContext, next_handler: MiddlewareHandler
    ) -> web.Response:
        """Process request with authentication and authorization.

        Args:
            request: aiohttp Request object
            context: Request context
            next_handler: Next middleware handler

        Returns:
            web.Response object
        """
        # Check if route requires authentication
        route_match = context.route_match
        if not route_match:
            # No route matched, continue (will be handled by routing error)
            return await next_handler(request, context)

        route = route_match.route
        if not route.auth_required:
            # Route doesn't require auth, continue
            return await next_handler(request, context)

        # Extract token
        token = self.extractor.extract(request)

        if not token:
            logger.info(
                "Authentication required but no token provided",
                extra={
                    "correlation_id": context.correlation_id,
                    "path": context.path,
                },
            )
            return web.json_response(
                {
                    "error": "invalid_token",
                    "message": "Authentication required",
                    "correlation_id": context.correlation_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate token
        session_data = await self.validator.validate(token)

        if not session_data:
            logger.info(
                "Invalid or expired token",
                extra={
                    "correlation_id": context.correlation_id,
                    "path": context.path,
                },
            )
            return web.json_response(
                {
                    "error": "invalid_token",
                    "message": "Session token is invalid or expired",
                    "correlation_id": context.correlation_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Populate context with user information
        context.user_id = session_data.user_id
        context.session_id = session_data.session_id
        context.roles = session_data.roles or []
        context.permissions = session_data.permissions or []
        context.authenticated = True

        # Check authorization
        if not self.authorizer.authorize(session_data, route.auth_roles):
            logger.warning(
                f"Authorization denied for user {session_data.user_id}",
                extra={
                    "correlation_id": context.correlation_id,
                    "user_id": session_data.user_id,
                    "required_roles": route.auth_roles,
                    "user_roles": session_data.roles,
                },
            )
            return web.json_response(
                {
                    "error": "forbidden",
                    "message": "Access denied",
                    "correlation_id": context.correlation_id,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                status=403,
            )

        # Handle token refresh if enabled
        new_token = None
        if self.refresher and self.config.session.refresh_enabled:
            session_data, new_token = await self.refresher.refresh(session_data)

        # Process request
        response = await next_handler(request, context)

        # Add new token to response if refreshed
        if new_token:
            response.set_cookie(
                self.config.session.cookie_name,
                new_token,
                max_age=self.config.session.token_ttl,
                httponly=True,
                secure=True,  # Always use secure in production
                samesite="Lax",
            )
            logger.debug(f"Set refreshed token in response for session {session_data.session_id}")

        return response
