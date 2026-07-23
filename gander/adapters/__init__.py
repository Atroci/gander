"""Adapter registry population. Importing this package registers every adapter.

To add a site: create gander/adapters/<site>.py with a SiteAdapter subclass,
then import and register it here.
"""
from ..adapter import register
from .idealista import IdealistaAdapter

register(IdealistaAdapter())
