"""DynamoDB-based storage for sessions and rate limiting.

This module provides DynamoDB implementations to replace Redis in AWS Lambda.
"""

import json
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from gateway.core.rate_limit import RateLimitStore
from gateway.core.session_store import SessionStore


class DynamoDBSessionStore(SessionStore):
    """DynamoDB-based session store (replaces Redis in Lambda)."""

    def __init__(self, table_name: str, region_name: str | None = None):
        """Initialize DynamoDB session store.

        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region name (optional, uses default if not provided)
        """
        self.table_name = table_name
        self.region_name = region_name
        self._dynamodb = None
        self._table = None

    async def connect(self) -> None:
        """Connect to DynamoDB."""
        # boto3 is synchronous, but we keep async interface for compatibility
        self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._dynamodb.Table(self.table_name)

    async def disconnect(self) -> None:
        """Disconnect from DynamoDB."""
        # boto3 doesn't require explicit disconnect
        self._dynamodb = None
        self._table = None

    async def get(self, key: str) -> str | None:
        """Get value from DynamoDB.

        Args:
            key: Session key

        Returns:
            Session data as JSON string or None if not found
        """
        try:
            response = self._table.get_item(Key={"session_id": key})
            if "Item" in response:
                # Check if TTL has expired (DynamoDB TTL deletion is async)
                ttl = response["Item"].get("ttl", 0)
                if ttl > 0 and ttl < int(time.time()):
                    return None
                return response["Item"].get("data")
            return None
        except ClientError as e:
            # Log error but don't raise to maintain availability
            print(f"DynamoDB get error: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set value in DynamoDB.

        Args:
            key: Session key
            value: Session data as JSON string
            ttl: Time-to-live in seconds (optional)
        """
        try:
            item = {
                "session_id": key,
                "data": value,
            }

            # Add TTL if provided
            if ttl:
                item["ttl"] = int(time.time()) + ttl

            self._table.put_item(Item=item)
        except ClientError as e:
            print(f"DynamoDB set error: {e}")
            raise

    async def delete(self, key: str) -> None:
        """Delete value from DynamoDB.

        Args:
            key: Session key
        """
        try:
            self._table.delete_item(Key={"session_id": key})
        except ClientError as e:
            print(f"DynamoDB delete error: {e}")
            # Don't raise, deletion failure is not critical

    async def exists(self, key: str) -> bool:
        """Check if key exists in DynamoDB.

        Args:
            key: Session key

        Returns:
            True if key exists and not expired, False otherwise
        """
        value = await self.get(key)
        return value is not None


class DynamoDBRateLimitStore(RateLimitStore):
    """DynamoDB-based rate limit store (replaces Redis in Lambda)."""

    def __init__(self, table_name: str, region_name: str | None = None):
        """Initialize DynamoDB rate limit store.

        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region name (optional, uses default if not provided)
        """
        self.table_name = table_name
        self.region_name = region_name
        self._dynamodb = None
        self._table = None

    async def connect(self) -> None:
        """Connect to DynamoDB."""
        self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._dynamodb.Table(self.table_name)

    async def disconnect(self) -> None:
        """Disconnect from DynamoDB."""
        self._dynamodb = None
        self._table = None

    async def is_healthy(self) -> bool:
        """Check if DynamoDB is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            self._table.meta.client.describe_table(TableName=self.table_name)
            return True
        except ClientError:
            return False

    async def get_count(self, key: str) -> int:
        """Get current count for rate limit key.

        Args:
            key: Rate limit key

        Returns:
            Current count
        """
        try:
            response = self._table.get_item(Key={"rate_limit_key": key})
            if "Item" in response:
                # Check if TTL has expired
                ttl = response["Item"].get("ttl", 0)
                if ttl > 0 and ttl < int(time.time()):
                    return 0
                return int(response["Item"].get("count", 0))
            return 0
        except ClientError as e:
            print(f"DynamoDB get_count error: {e}")
            return 0

    async def increment(self, key: str, amount: int = 1, ttl: int | None = None) -> int:
        """Increment count for rate limit key.

        Args:
            key: Rate limit key
            amount: Amount to increment
            ttl: Time-to-live in seconds (optional)

        Returns:
            New count value
        """
        try:
            # Use atomic update
            update_expr = "SET #count = if_not_exists(#count, :zero) + :inc"
            expr_attr_names = {"#count": "count"}
            expr_attr_values = {":zero": 0, ":inc": amount}

            if ttl:
                update_expr += ", #ttl = :ttl"
                expr_attr_names["#ttl"] = "ttl"
                expr_attr_values[":ttl"] = int(time.time()) + ttl

            response = self._table.update_item(
                Key={"rate_limit_key": key},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="UPDATED_NEW",
            )

            return int(response["Attributes"]["count"])
        except ClientError as e:
            print(f"DynamoDB increment error: {e}")
            # Return 0 to fail open
            return 0

    async def set_count(self, key: str, count: int, ttl: int | None = None) -> None:
        """Set count for rate limit key.

        Args:
            key: Rate limit key
            count: Count value
            ttl: Time-to-live in seconds (optional)
        """
        try:
            item = {
                "rate_limit_key": key,
                "count": count,
            }

            if ttl:
                item["ttl"] = int(time.time()) + ttl

            self._table.put_item(Item=item)
        except ClientError as e:
            print(f"DynamoDB set_count error: {e}")
            # Don't raise to fail open

    async def reset(self, key: str) -> None:
        """Reset count for rate limit key.

        Args:
            key: Rate limit key
        """
        try:
            self._table.delete_item(Key={"rate_limit_key": key})
        except ClientError as e:
            print(f"DynamoDB reset error: {e}")
            # Don't raise, reset failure is not critical

    async def get_state(self, key: str) -> dict[str, Any]:
        """Get complete state for rate limit key.

        Args:
            key: Rate limit key

        Returns:
            State dictionary with count, tokens, last_update, etc.
        """
        try:
            response = self._table.get_item(Key={"rate_limit_key": key})
            if "Item" in response:
                item = response["Item"]
                # Check if TTL has expired
                ttl = item.get("ttl", 0)
                if ttl > 0 and ttl < int(time.time()):
                    return {}

                # Return state (deserialize JSON if needed)
                state_json = item.get("state", "{}")
                if isinstance(state_json, str):
                    return json.loads(state_json)
                return state_json
            return {}
        except ClientError as e:
            print(f"DynamoDB get_state error: {e}")
            return {}

    async def set_state(self, key: str, state: dict[str, Any], ttl: int | None = None) -> None:
        """Set complete state for rate limit key.

        Args:
            key: Rate limit key
            state: State dictionary
            ttl: Time-to-live in seconds (optional)
        """
        try:
            item = {
                "rate_limit_key": key,
                "state": json.dumps(state),
            }

            if ttl:
                item["ttl"] = int(time.time()) + ttl

            self._table.put_item(Item=item)
        except ClientError as e:
            print(f"DynamoDB set_state error: {e}")
            # Don't raise to fail open
