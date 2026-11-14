"""Gives every requests call a default 10-second timeout, since requests has none.
Imported for its side effect by services/billing; it patches requests for the whole process."""
import requests

_original = requests.Session.request


def _request_with_timeout(self, method, url, **kwargs):
    kwargs.setdefault("timeout", 10)
    return _original(self, method, url, **kwargs)


requests.Session.request = _request_with_timeout
