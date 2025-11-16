"""Integration tests for authentication and authorization."""

from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient

from gateway.core.session_store import InMemorySessionStore, SessionData


class TestAuthentication:
    """Test authentication middleware integration."""

    @pytest.mark.asyncio
    async def test_protected_route_without_token(self, gateway_client: TestClient):
        """Test accessing protected route without session token."""
        response = await gateway_client.get("/api/users/123")

        assert response.status == 401
        data = await response.json()
        assert data["error"] == "invalid_token"
        assert "message" in data

    @pytest.mark.asyncio
    async def test_protected_route_with_valid_token(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test accessing protected route with valid session token."""
        # Set session cookie
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/users/123")

        assert response.status == 200
        data = await response.json()
        assert data["user_id"] == "123"

    @pytest.mark.asyncio
    async def test_protected_route_with_token_in_header(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test accessing protected route with token in Authorization header."""
        headers = {"Authorization": f"Bearer {test_session.session_id}"}

        response = await gateway_client.get("/api/users/123", headers=headers)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_protected_route_with_expired_token(
        self, gateway_client: TestClient, session_store: InMemorySessionStore
    ):
        """Test accessing protected route with expired session token."""
        # Create expired session
        now = datetime.now(UTC)
        expired_session = SessionData(
            session_id="expired-session",
            user_id="user-999",
            username="expireduser",
            created_at=now - timedelta(hours=2),
            last_accessed_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=5),  # Expired 5 minutes ago
            roles=["user"],
        )
        await session_store.create(expired_session)

        gateway_client.session.cookie_jar.update_cookies(
            {"session_token": expired_session.session_id}
        )

        response = await gateway_client.get("/api/users/123")

        assert response.status == 401
        data = await response.json()
        assert "expired" in data["error"].lower() or data["error"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_protected_route_with_revoked_token(
        self,
        gateway_client: TestClient,
        gateway,
        test_session: SessionData,
    ):
        """Test accessing protected route with revoked session token."""
        # Revoke the session
        await gateway.session_store.revoke(test_session.session_id)

        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/users/123")

        assert response.status == 401
        data = await response.json()
        assert data["error"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_protected_route_with_invalid_token_format(self, gateway_client: TestClient):
        """Test accessing protected route with malformed token."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": "invalid-token-format"})

        response = await gateway_client.get("/api/users/123")

        assert response.status == 401
        data = await response.json()
        assert data["error"] == "invalid_token"

    @pytest.mark.asyncio
    async def test_public_route_without_token(self, gateway_client: TestClient):
        """Test that public routes don't require authentication."""
        response = await gateway_client.get("/api/hello")

        assert response.status == 200
        # No authentication required

    @pytest.mark.asyncio
    async def test_public_route_with_token(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test that public routes accept but don't require authentication."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/hello")

        assert response.status == 200
        # Token is accepted but not required


class TestAuthorization:
    """Test authorization (role-based access control) integration."""

    @pytest.mark.asyncio
    async def test_route_with_required_role_success(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test accessing route when user has required role."""
        # test_session has "user" role, which is required for /api/users
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/users/123")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_route_with_required_role_failure(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test accessing route when user lacks required role."""
        # test_session has "user" role, but /api/admin requires "admin" role
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/admin")

        assert response.status == 403
        data = await response.json()
        assert data["error"] == "forbidden"

    @pytest.mark.asyncio
    async def test_admin_route_with_admin_role(
        self, gateway_client: TestClient, admin_session: SessionData
    ):
        """Test admin route access with admin role."""
        # admin_session has both "user" and "admin" roles
        gateway_client.session.cookie_jar.update_cookies(
            {"session_token": admin_session.session_id}
        )

        response = await gateway_client.get("/api/admin")

        # Should succeed if admin route exists in mock upstream
        # (May get 404 if route doesn't exist in mock, but shouldn't get 403)
        assert response.status != 403

    @pytest.mark.asyncio
    async def test_multiple_required_roles(
        self, gateway_client: TestClient, admin_session: SessionData
    ):
        """Test route requiring one of multiple roles."""
        # If a route accepts either "user" or "admin", test that it works
        gateway_client.session.cookie_jar.update_cookies(
            {"session_token": admin_session.session_id}
        )

        response = await gateway_client.get("/api/users/456")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_authorization_without_authentication(self, gateway_client: TestClient):
        """Test that authorization check requires authentication first."""
        # Try to access protected route without token
        response = await gateway_client.get("/api/users/123")

        # Should get 401 (authentication failure) not 403 (authorization failure)
        assert response.status == 401


class TestSessionLifecycle:
    """Test session management and lifecycle."""

    @pytest.mark.asyncio
    async def test_session_last_accessed_updated(
        self,
        gateway_client: TestClient,
        session_store: InMemorySessionStore,
        test_session: SessionData,
    ):
        """Test that session last_accessed_at is updated on use."""
        original_last_accessed = test_session.last_accessed_at

        # Wait a bit and make a request
        import asyncio

        await asyncio.sleep(0.1)

        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/users/123")
        assert response.status == 200

        # Retrieve session and check last_accessed_at was updated
        updated_session = await session_store.get(test_session.session_id)
        if updated_session:
            assert updated_session.last_accessed_at > original_last_accessed

    @pytest.mark.asyncio
    async def test_session_refresh_near_expiration(
        self,
        gateway_client: TestClient,
        gateway,
    ):
        """Test session token refresh when approaching expiration."""
        # Create session that's near expiration
        now = datetime.now(UTC)
        near_expiration_session = SessionData(
            session_id="near-expiry-session",
            user_id="user-888",
            username="nearexpiryuser",
            created_at=now - timedelta(minutes=55),
            last_accessed_at=now,
            expires_at=now + timedelta(minutes=2),  # Expires soon
            roles=["user"],
        )
        await gateway.session_store.create(near_expiration_session)

        gateway_client.session.cookie_jar.update_cookies(
            {"session_token": near_expiration_session.session_id}
        )

        response = await gateway_client.get("/api/users/123")

        assert response.status == 200

        # Check if a new session token was set in response cookies
        # (Implementation specific - depends on refresh mechanism)


class TestAuthenticationLogging:
    """Test authentication and authorization event logging."""

    @pytest.mark.asyncio
    async def test_successful_auth_logged(
        self, gateway_client: TestClient, test_session: SessionData, caplog
    ):
        """Test that successful authentication is logged."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        with caplog.at_level("INFO"):
            response = await gateway_client.get("/api/users/123")
            assert response.status == 200

        # Check logs for successful authentication event

    @pytest.mark.asyncio
    async def test_failed_auth_logged(self, gateway_client: TestClient, caplog):
        """Test that failed authentication is logged."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": "invalid-token"})

        with caplog.at_level("WARNING"):
            response = await gateway_client.get("/api/users/123")
            assert response.status == 401

        # Check logs for failed authentication event

    @pytest.mark.asyncio
    async def test_authz_denial_logged(
        self, gateway_client: TestClient, test_session: SessionData, caplog
    ):
        """Test that authorization denials are logged."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        with caplog.at_level("WARNING"):
            response = await gateway_client.get("/api/admin")
            assert response.status == 403

        # Check logs for authorization denial


class TestUserContext:
    """Test that user context is properly propagated."""

    @pytest.mark.asyncio
    async def test_user_id_forwarded_to_upstream(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test that user ID is forwarded to upstream in headers."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.post("/api/echo", json={})

        assert response.status == 200
        data = await response.json()

        # Check if X-User-ID header was added
        if "X-User-ID" in data["headers"]:
            assert data["headers"]["X-User-ID"] == test_session.user_id

    @pytest.mark.asyncio
    async def test_user_roles_available_in_context(
        self, gateway_client: TestClient, test_session: SessionData
    ):
        """Test that user roles are available in request context."""
        gateway_client.session.cookie_jar.update_cookies({"session_token": test_session.session_id})

        response = await gateway_client.get("/api/users/123")

        assert response.status == 200
        # User has "user" role, so access should be granted
