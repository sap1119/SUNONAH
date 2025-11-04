from abc import ABC, abstractmethod


class BaseCache(ABC):
    @abstractmethod
    def set(self, *args, **kwargs):
        """Set a value in the cache"""
        pass

    @abstractmethod
    def get(self, *args, **kwargs):
        """Get a value from the cache"""
        pass