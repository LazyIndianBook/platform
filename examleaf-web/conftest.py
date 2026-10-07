import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()  # allauth's rate limits and axes live in the cache


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path  # the health check's storage probe and any upload write here
