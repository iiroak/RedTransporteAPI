"""Storage abstraction — defines the interface for auth persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from red_transporte_api.auth.models import APISettings, TokenRecord


class AuthStorage(ABC):
    @abstractmethod
    def initialize(
        self,
        initial_public_api_enabled: bool = True,
        initial_public_ip_limit: int = 20,
    ) -> None:
        """Create tables if they don't exist and seed initial settings from env."""
        raise NotImplementedError

    @abstractmethod
    def get_settings(self) -> APISettings:
        raise NotImplementedError

    @abstractmethod
    def update_settings(self, settings: APISettings) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_token(self, name: str, token_hash: str, is_unlimited: bool, requests_per_minute: int, allow_gtfs: bool, allow_ibus: bool, allow_red_web: bool, allow_raptor: bool) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_token_by_hash(self, token_hash: str) -> Optional[TokenRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_tokens(self) -> list[TokenRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_token_by_id(self, token_id: int) -> Optional[TokenRecord]:
        raise NotImplementedError

    @abstractmethod
    def update_token(self, token_id: int, name: Optional[str] = None, enabled: Optional[bool] = None, is_unlimited: Optional[bool] = None, requests_per_minute: Optional[int] = None, allow_gtfs: Optional[bool] = None, allow_ibus: Optional[bool] = None, allow_red_web: Optional[bool] = None, allow_raptor: Optional[bool] = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_token(self, token_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_token_last_used(self, token_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def increment_rate_counter(self, subject_type: str, subject_key: str, resource_type: str, window_start: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_rate_counter(self, subject_type: str, subject_key: str, resource_type: str, window_start: int) -> int:
        raise NotImplementedError

    @abstractmethod
    def consume_rate_counter(self, subject_type: str, subject_key: str, resource_type: str, window_start: int, limit: int) -> Optional[int]:
        """Atomically increment the counter when it is below *limit*.

        Returns the new counter value when the increment was applied, or None
        when the counter is already at or above *limit*.
        """
        raise NotImplementedError