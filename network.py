"""Bound requests made by the locked requests-based API clients."""
import requests

HTTP_TIMEOUT = (10, 60)  # connect, read (seconds)


class TimeoutSession(requests.Session):
    def request(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = HTTP_TIMEOUT
        return super().request(method, url, **kwargs)
