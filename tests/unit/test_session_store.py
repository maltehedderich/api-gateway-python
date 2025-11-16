"""Unit tests for session store module."""

from datetime import datetime, timedelta

import pytest

from gateway.core.session_store import InMemorySessionStore, SessionData


class TestSessionData:
    """Tests for SessionData model."""

    def test_session_data_creation(self):
        """Test creating session data."""
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=1)

        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=expires_at,
            roles=["user"],
            permissions=["read:data"],
        )

        assert session.session_id == "sess-123"
        assert session.user_id == "user-456"
        assert session.username == "testuser"
        assert session.roles == ["user"]
        assert session.permissions == ["read:data"]
        assert not session.revoked

    def test_is_expired(self):
        """Test session expiration check."""
        now = datetime.utcnow()

        # Not expired
        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert not session.is_expired()

        # Expired
        expired_session = SessionData(
            session_id="sess-456",
            user_id="user-789",
            username="expireduser",
            created_at=now - timedelta(hours=2),
            last_accessed_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=1),
        )
        assert expired_session.is_expired()

    def test_is_valid(self):
        """Test session validity check."""
        now = datetime.utcnow()

        # Valid session
        valid_session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert valid_session.is_valid()

        # Revoked session
        revoked_session = SessionData(
            session_id="sess-789",
            user_id="user-123",
            username="revokeduser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
            revoked=True,
        )
        assert not revoked_session.is_valid()

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=1)

        session = SessionData(
            session_id="sess-123",
            user_id="user-456",
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=expires_at,
            roles=["user", "admin"],
            permissions=["read:data", "write:data"],
        )

        # Serialize
        session_dict = session.to_dict()
        assert isinstance(session_dict["created_at"], str)
        assert isinstance(session_dict["expires_at"], str)

        # Deserialize
        restored_session = SessionData.from_dict(session_dict)
        assert restored_session.session_id == session.session_id
        assert restored_session.user_id == session.user_id
        assert restored_session.username == session.username
        assert restored_session.roles == session.roles
        assert restored_session.permissions == session.permissions


class TestInMemorySessionStore:
    """Tests for InMemorySessionStore."""

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

    async def test_create_session(self, store, sample_session):
        """Test creating a session."""
        success = await store.create(sample_session)
        assert success

        # Verify we can retrieve it
        retrieved = await store.get(sample_session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == sample_session.session_id
        assert retrieved.user_id == sample_session.user_id

    async def test_get_nonexistent_session(self, store):
        """Test getting a session that doesn't exist."""
        session = await store.get("nonexistent")
        assert session is None

    async def test_update_session(self, store, sample_session):
        """Test updating a session."""
        await store.create(sample_session)

        # Update session
        sample_session.roles.append("admin")
        success = await store.update(sample_session)
        assert success

        # Verify update
        retrieved = await store.get(sample_session.session_id)
        assert "admin" in retrieved.roles

    async def test_delete_session(self, store, sample_session):
        """Test deleting a session."""
        await store.create(sample_session)

        # Delete
        success = await store.delete(sample_session.session_id)
        assert success

        # Verify deleted
        retrieved = await store.get(sample_session.session_id)
        assert retrieved is None

    async def test_revoke_session(self, store, sample_session):
        """Test revoking a session."""
        await store.create(sample_session)

        # Revoke
        success = await store.revoke(sample_session.session_id)
        assert success

        # Verify revoked
        is_revoked = await store.is_revoked(sample_session.session_id)
        assert is_revoked

        retrieved = await store.get(sample_session.session_id)
        assert retrieved.revoked

    async def test_revoke_all_user_sessions(self, store):
        """Test revoking all sessions for a user."""
        now = datetime.utcnow()
        user_id = "user-123"

        # Create multiple sessions for same user
        session1 = SessionData(
            session_id="sess-1",
            user_id=user_id,
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
        )
        session2 = SessionData(
            session_id="sess-2",
            user_id=user_id,
            username="testuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
        )

        await store.create(session1)
        await store.create(session2)

        # Revoke all
        count = await store.revoke_all_user_sessions(user_id)
        assert count == 2

        # Verify both revoked
        assert await store.is_revoked("sess-1")
        assert await store.is_revoked("sess-2")

    async def test_cleanup_expired(self, store):
        """Test cleaning up expired sessions."""
        now = datetime.utcnow()

        # Create expired session
        expired_session = SessionData(
            session_id="sess-expired",
            user_id="user-123",
            username="expireduser",
            created_at=now - timedelta(hours=2),
            last_accessed_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=1),
        )

        # Create valid session
        valid_session = SessionData(
            session_id="sess-valid",
            user_id="user-456",
            username="validuser",
            created_at=now,
            last_accessed_at=now,
            expires_at=now + timedelta(hours=1),
        )

        await store.create(expired_session)
        await store.create(valid_session)

        # Cleanup
        count = await store.cleanup_expired()
        assert count == 1

        # Verify expired session is gone
        assert await store.get("sess-expired") is None

        # Verify valid session still exists
        assert await store.get("sess-valid") is not None

    async def test_get_expired_session_returns_none(self, store):
        """Test that getting an expired session returns None."""
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

        # Getting expired session should return None and clean it up
        retrieved = await store.get("sess-expired")
        assert retrieved is None
