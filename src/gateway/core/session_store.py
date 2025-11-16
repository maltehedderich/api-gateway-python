"""Session store module for managing session state.

This module provides:
- Session store interface and Redis implementation
- Session CRUD operations (create, read, update, delete)
- Session expiration and cleanup
- Revocation list management
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """Session data model.

    Represents a session with user identity and permissions.
    """

    session_id: str
    user_id: str
    username: str
    created_at: datetime
    last_accessed_at: datetime
    expires_at: datetime
    revoked: bool = False
    roles: List[str] = None
    permissions: List[str] = None
    ip_address: Optional[str] = None
    device_fingerprint: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self) -> None:
        """Initialize default values for mutable fields."""
        if self.roles is None:
            self.roles = []
        if self.permissions is None:
            self.permissions = []
        if self.metadata is None:
            self.metadata = {}

    def is_expired(self) -> bool:
        """Check if session is expired.

        Returns:
            True if session is expired, False otherwise
        """
        return datetime.utcnow() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if session is valid (not expired and not revoked).

        Returns:
            True if session is valid, False otherwise
        """
        return not self.is_expired() and not self.revoked

    def to_dict(self) -> Dict[str, Any]:
        """Convert session data to dictionary.

        Returns:
            Dictionary representation of session data
        """
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data["created_at"] = self.created_at.isoformat()
        data["last_accessed_at"] = self.last_accessed_at.isoformat()
        data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create session data from dictionary.

        Args:
            data: Dictionary representation of session data

        Returns:
            SessionData instance
        """
        # Convert ISO format strings to datetime objects
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["last_accessed_at"] = datetime.fromisoformat(data["last_accessed_at"])
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


class SessionStore(ABC):
    """Abstract base class for session storage."""

    @abstractmethod
    async def create(self, session_data: SessionData) -> bool:
        """Create a new session.

        Args:
            session_data: Session data to store

        Returns:
            True if created successfully, False otherwise
        """
        pass

    @abstractmethod
    async def get(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found, None otherwise
        """
        pass

    @abstractmethod
    async def update(self, session_data: SessionData) -> bool:
        """Update an existing session.

        Args:
            session_data: Session data to update

        Returns:
            True if updated successfully, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    async def revoke(self, session_id: str) -> bool:
        """Revoke a session.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked successfully, False otherwise
        """
        pass

    @abstractmethod
    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        pass

    @abstractmethod
    async def is_revoked(self, session_id: str) -> bool:
        """Check if a session is revoked.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked, False otherwise
        """
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        pass


class RedisSessionStore(SessionStore):
    """Redis-based session store implementation."""

    def __init__(self, redis_url: str, key_prefix: str = "session:"):
        """Initialize Redis session store.

        Args:
            redis_url: Redis connection URL
            key_prefix: Prefix for session keys
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.client: Optional[redis.Redis] = None
        self.revocation_key_prefix = "revoked:"

    async def connect(self) -> None:
        """Connect to Redis."""
        if self.client is None:
            self.client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Connected to Redis session store at {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from Redis session store")

    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for session.

        Args:
            session_id: Session identifier

        Returns:
            Redis key
        """
        return f"{self.key_prefix}{session_id}"

    def _revocation_key(self, session_id: str) -> str:
        """Generate Redis key for revocation.

        Args:
            session_id: Session identifier

        Returns:
            Redis key for revocation
        """
        return f"{self.key_prefix}{self.revocation_key_prefix}{session_id}"

    def _user_sessions_key(self, user_id: str) -> str:
        """Generate Redis key for user sessions set.

        Args:
            user_id: User identifier

        Returns:
            Redis key for user sessions
        """
        return f"{self.key_prefix}user:{user_id}:sessions"

    async def create(self, session_data: SessionData) -> bool:
        """Create a new session in Redis.

        Args:
            session_data: Session data to store

        Returns:
            True if created successfully, False otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Calculate TTL in seconds
            ttl = int((session_data.expires_at - datetime.utcnow()).total_seconds())
            if ttl <= 0:
                logger.warning(f"Session {session_data.session_id} already expired, not creating")
                return False

            # Store session data
            session_key = self._session_key(session_data.session_id)
            session_json = json.dumps(session_data.to_dict())

            # Set with expiration
            await self.client.set(session_key, session_json, ex=ttl)

            # Add to user sessions set
            user_sessions_key = self._user_sessions_key(session_data.user_id)
            await self.client.sadd(user_sessions_key, session_data.session_id)
            await self.client.expire(user_sessions_key, ttl)

            logger.debug(f"Created session {session_data.session_id} for user {session_data.user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create session {session_data.session_id}: {e}")
            return False

    async def get(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session from Redis.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found, None otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            session_key = self._session_key(session_id)
            session_json = await self.client.get(session_key)

            if not session_json:
                return None

            session_dict = json.loads(session_json)
            session_data = SessionData.from_dict(session_dict)

            # Check if expired (shouldn't happen due to Redis TTL, but defensive check)
            if session_data.is_expired():
                await self.delete(session_id)
                return None

            return session_data

        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def update(self, session_data: SessionData) -> bool:
        """Update session in Redis.

        Args:
            session_data: Session data to update

        Returns:
            True if updated successfully, False otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Check if session exists
            session_key = self._session_key(session_data.session_id)
            exists = await self.client.exists(session_key)

            if not exists:
                logger.warning(f"Session {session_data.session_id} not found for update")
                return False

            # Calculate remaining TTL
            ttl = int((session_data.expires_at - datetime.utcnow()).total_seconds())
            if ttl <= 0:
                await self.delete(session_data.session_id)
                return False

            # Update session data
            session_json = json.dumps(session_data.to_dict())
            await self.client.set(session_key, session_json, ex=ttl)

            logger.debug(f"Updated session {session_data.session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update session {session_data.session_id}: {e}")
            return False

    async def delete(self, session_id: str) -> bool:
        """Delete session from Redis.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Get session to find user_id
            session_data = await self.get(session_id)

            # Delete session key
            session_key = self._session_key(session_id)
            await self.client.delete(session_key)

            # Remove from user sessions set if we found the session
            if session_data:
                user_sessions_key = self._user_sessions_key(session_data.user_id)
                await self.client.srem(user_sessions_key, session_id)

            # Delete revocation key if exists
            revocation_key = self._revocation_key(session_id)
            await self.client.delete(revocation_key)

            logger.debug(f"Deleted session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def revoke(self, session_id: str) -> bool:
        """Revoke a session by marking it as revoked.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked successfully, False otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Get session to find expiration time
            session_data = await self.get(session_id)

            if not session_data:
                logger.warning(f"Session {session_id} not found for revocation")
                return False

            # Mark session as revoked
            session_data.revoked = True
            await self.update(session_data)

            # Add to revocation set with TTL matching session expiration
            ttl = int((session_data.expires_at - datetime.utcnow()).total_seconds())
            if ttl > 0:
                revocation_key = self._revocation_key(session_id)
                await self.client.set(revocation_key, "1", ex=ttl)

            logger.info(f"Revoked session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke session {session_id}: {e}")
            return False

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Get all session IDs for user
            user_sessions_key = self._user_sessions_key(user_id)
            session_ids = await self.client.smembers(user_sessions_key)

            count = 0
            for session_id in session_ids:
                if await self.revoke(session_id):
                    count += 1

            logger.info(f"Revoked {count} sessions for user {user_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to revoke sessions for user {user_id}: {e}")
            return 0

    async def is_revoked(self, session_id: str) -> bool:
        """Check if a session is revoked.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked, False otherwise
        """
        if not self.client:
            raise RuntimeError("Session store not connected")

        try:
            # Check revocation key
            revocation_key = self._revocation_key(session_id)
            exists = await self.client.exists(revocation_key)

            if exists:
                return True

            # Also check session data
            session_data = await self.get(session_id)
            return session_data.revoked if session_data else False

        except Exception as e:
            logger.error(f"Failed to check revocation status for session {session_id}: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """Clean up expired sessions.

        Note: Redis automatically handles expiration via TTL, so this is a no-op.
        Included for interface completeness.

        Returns:
            0 (Redis handles cleanup automatically)
        """
        # Redis handles expiration automatically
        return 0


class InMemorySessionStore(SessionStore):
    """In-memory session store for testing and development."""

    def __init__(self) -> None:
        """Initialize in-memory session store."""
        self.sessions: Dict[str, SessionData] = {}
        self.user_sessions: Dict[str, List[str]] = {}
        self.revoked: set[str] = set()

    async def connect(self) -> None:
        """Connect (no-op for in-memory store)."""
        logger.info("In-memory session store ready")

    async def disconnect(self) -> None:
        """Disconnect (no-op for in-memory store)."""
        self.sessions.clear()
        self.user_sessions.clear()
        self.revoked.clear()

    async def create(self, session_data: SessionData) -> bool:
        """Create a new session.

        Args:
            session_data: Session data to store

        Returns:
            True if created successfully
        """
        self.sessions[session_data.session_id] = session_data

        # Add to user sessions
        if session_data.user_id not in self.user_sessions:
            self.user_sessions[session_data.user_id] = []
        self.user_sessions[session_data.user_id].append(session_data.session_id)

        return True

    async def get(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found, None otherwise
        """
        session_data = self.sessions.get(session_id)

        if session_data and session_data.is_expired():
            await self.delete(session_id)
            return None

        return session_data

    async def update(self, session_data: SessionData) -> bool:
        """Update session.

        Args:
            session_data: Session data to update

        Returns:
            True if updated successfully
        """
        if session_data.session_id in self.sessions:
            self.sessions[session_data.session_id] = session_data
            return True
        return False

    async def delete(self, session_id: str) -> bool:
        """Delete session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully
        """
        session_data = self.sessions.pop(session_id, None)

        if session_data:
            # Remove from user sessions
            if session_data.user_id in self.user_sessions:
                try:
                    self.user_sessions[session_data.user_id].remove(session_id)
                except ValueError:
                    pass

        self.revoked.discard(session_id)
        return True

    async def revoke(self, session_id: str) -> bool:
        """Revoke a session.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked successfully
        """
        session_data = await self.get(session_id)

        if session_data:
            session_data.revoked = True
            self.revoked.add(session_id)
            return True

        return False

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        session_ids = self.user_sessions.get(user_id, []).copy()
        count = 0

        for session_id in session_ids:
            if await self.revoke(session_id):
                count += 1

        return count

    async def is_revoked(self, session_id: str) -> bool:
        """Check if a session is revoked.

        Args:
            session_id: Session identifier

        Returns:
            True if revoked, False otherwise
        """
        return session_id in self.revoked

    async def cleanup_expired(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        expired = [
            session_id
            for session_id, session_data in self.sessions.items()
            if session_data.is_expired()
        ]

        for session_id in expired:
            await self.delete(session_id)

        return len(expired)
