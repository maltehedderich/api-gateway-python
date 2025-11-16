"""Unit tests for authentication middleware."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from aiohttp import web

from gateway.core.config import GatewayConfig, RouteConfig, SessionConfig
from gateway.core.middleware import RequestContext
from gateway.core.routing import RouteMatch
from gateway.core.session_store import InMemorySessionStore, SessionData
from gateway.middleware.auth import (
    TokenExtractor,
    TokenValidator,
    TokenRefresher,
    Authorizer,
    AuthenticationMiddleware,
)


class TestTokenExtractor:
    """Tests for TokenExtractor."""

    def test_extract_from_cookie(self):
        """Test extracting token from cookie."""
        request = Mock(spec=web.Request)
        request.cookies = {"session_token": "test-token-123"}

        extractor = TokenExtractor(cookie_name="session_token")
        token = extractor.extract_from_cookie(request)

        assert token == "test-token-123"

    def test_extract_from_cookie_not_found(self):
        """Test extracting token when cookie doesn't exist."""
        request = Mock(spec=web.Request)
        request.cookies = {}

        extractor = TokenExtractor(cookie_name="session_token")
        token = extractor.extract_from_cookie(request)

        assert token is None

    def test_extract_from_header(self):
        """Test extracting token from Authorization header."""
        request = Mock(spec=web.Request)
        request.headers = {"Authorization": "Bearer test-token-456"}

        extractor = TokenExtractor()
        token = extractor.extract_from_header(request)

        assert token == "test-token-456"

    def test_extract_from_header_not_found(self):
        """Test extracting token when Authorization header doesn't exist."""
        request = Mock(spec=web.Request)
        request.headers = {}

        extractor = TokenExtractor()
        token = extractor.extract_from_header(request)

        assert token is None

    def test_extract_prefers_cookie(self):
        """Test that extract prefers cookie over header."""
        request = Mock(spec=web.Request)
        request.cookies = {"session_token": "cookie-token"}
        request.headers = {"Authorization": "Bearer header-token"}

        extractor = TokenExtractor(cookie_name="session_token")
        token = extractor.extract(request)

        assert token == "cookie-token"

    def test_extract_fallback_to_header(self):
        """Test that extract falls back to header when no cookie."""
        request = Mock(spec=web.Request)
        request.cookies = {}
        request.headers = {"Authorization": "Bearer header-token"}

        extractor = TokenExtractor(cookie_name="session_token")
        token = extractor.extract(request)

        assert token == "header-token"


class TestTokenValidator:
    """Tests for TokenValidator."""

    @pytest.fixture
    async def store(self):
        """Create in-memory session store."""
        store = InMemorySessionStore()
        await store.connect()
        yield store
        await store.disconnect()

    @pytest.fixture
    def sample_session(self):
        """Create sample session data."""
        now = datetime.utcnow()
        return SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["user"],
            permissions=["read:data"],
        )

    async def test_validate_opaque_token_success(self, store, sample_session):
        """Test validating a valid opaque token."""
        await store.create(sample_session)

        validator = TokenValidator(session_store=store, use_signed_tokens=False)
        session_data = await validator.validate(sample_session.session_id)

        assert session_data is not None
        assert session_data.session_id == sample_session.session_id
        assert session_data.user_id == sample_session.user_id

    async def test_validate_opaque_token_not_found(self, store):
        """Test validating a token that doesn't exist."""
        validator = TokenValidator(session_store=store, use_signed_tokens=False)
        session_data = await validator.validate("nonexistent-token")

        assert session_data is None

    async def test_validate_opaque_token_revoked(self, store, sample_session):
        """Test validating a revoked token."""
        await store.create(sample_session)
        await store.revoke(sample_session.session_id)

        validator = TokenValidator(session_store=store, use_signed_tokens=False)
        session_data = await validator.validate(sample_session.session_id)

        assert session_data is None

    async def test_validate_opaque_token_expired(self, store):
        """Test validating an expired token."""
        now = datetime.utcnow()
        expired_session = SessionData(
            session_id="sess-expired",
            user_id="user-123",
            username="expireduser",
            created_at=now - timedelta(hours=2),
            last_accessed_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=1),
        )
        await store.create(expired_session)

        validator = TokenValidator(session_store=store, use_signed_tokens=False)
        session_data = await validator.validate(expired_session.session_id)

        assert session_data is None

    async def test_validate_signed_token_success(self, store):
        """Test validating a valid signed token."""
        secret = "test-secret-key"
        now = datetime.utcnow()

        # Create a refresher to generate a signed token
        refresher = TokenRefresher(
            session_store=store,
            token_ttl=3600,
            signing_secret=secret,
            use_signed_tokens=True,
        )

        sample_session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["user"],
            permissions=["read:data"],
        )

        signed_token = refresher._generate_signed_token(sample_session)

        # Validate the signed token
        validator = TokenValidator(
            session_store=store,
            signing_secret=secret,
            use_signed_tokens=True,
        )
        session_data = await validator.validate(signed_token)

        assert session_data is not None
        assert session_data.user_id == "user-456"
        assert session_data.roles == ["user"]

    async def test_validate_signed_token_invalid_signature(self, store):
        """Test validating a signed token with invalid signature."""
        validator = TokenValidator(
            session_store=store,
            signing_secret="test-secret",
            use_signed_tokens=True,
        )

        # Create a token with invalid format
        invalid_token = "invalid.signature"
        session_data = await validator.validate(invalid_token)

        assert session_data is None


class TestTokenRefresher:
    """Tests for TokenRefresher."""

    @pytest.fixture
    async def store(self):
        """Create in-memory session store."""
        store = InMemorySessionStore()
        await store.connect()
        yield store
        await store.disconnect()

    async def test_should_refresh_true(self, store):
        """Test should_refresh returns True when near expiration."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(seconds=60),  # Expires in 60 seconds
        )

        refresher = TokenRefresher(
            session_store=store,
            refresh_threshold=300,  # Refresh if < 5 minutes remaining
            token_ttl=3600,
        )

        assert refresher.should_refresh(session)

    async def test_should_refresh_false(self, store):
        """Test should_refresh returns False when plenty of time remaining."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),  # Expires in 1 hour
        )

        refresher = TokenRefresher(
            session_store=store,
            refresh_threshold=300,  # Refresh if < 5 minutes remaining
            token_ttl=3600,
        )

        assert not refresher.should_refresh(session)

    async def test_refresh_session(self, store):
        """Test refreshing a session."""
        now = datetime.utcnow()
        old_expires_at = now + timedelta(seconds=60)
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=old_expires_at,  # Near expiration
        )
        await store.create(session)

        refresher = TokenRefresher(
            session_store=store,
            refresh_threshold=300,
            token_ttl=3600,
        )

        updated_session, new_token = await refresher.refresh(session)

        assert new_token is not None
        # Check that the new expiration is significantly later (should be ~3600 seconds from now)
        assert (updated_session.expires_at - datetime.utcnow()).total_seconds() > 3500


class TestAuthorizer:
    """Tests for Authorizer."""

    def test_authorize_success(self):
        """Test authorization with matching role."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["user", "admin"],
        )

        authorizer = Authorizer()
        assert authorizer.authorize(session, ["admin"])

    def test_authorize_failure(self):
        """Test authorization with no matching role."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["user"],
        )

        authorizer = Authorizer()
        assert not authorizer.authorize(session, ["admin"])

    def test_authorize_no_roles_required(self):
        """Test authorization when no roles required."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=[],
        )

        authorizer = Authorizer()
        assert authorizer.authorize(session, [])

    def test_authorize_multiple_required_roles(self):
        """Test authorization with multiple required roles (any match)."""
        now = datetime.utcnow()
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            roles=["user"],
        )

        authorizer = Authorizer()
        # Should pass because user has "user" role (even though they don't have "admin")
        assert authorizer.authorize(session, ["user", "admin"])
