"""Every list the API gives is bounded (RESILIENCE.md, request limits): pages of 200 at most, a search of five words,
a product's reviews."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from api import shop as shop_api
from api import urls
from api.pagination import PageNumberPagination
from api.tests import make_paper
from shop.factories import ProductFactory
from shop.models import Review

pytestmark = pytest.mark.django_db


def test_every_collection_of_the_api_is_paginated_at_200_a_page_at_most():
    for router in (urls.router, urls.store_router, urls.shipping_router):
        for prefix, viewset, _ in router.registry:
            assert viewset.pagination_class is not None, prefix
            assert issubclass(viewset.pagination_class, PageNumberPagination), prefix
    assert PageNumberPagination.max_page_size == 200


def test_a_search_of_many_words_searches_five_of_them():
    make_paper()
    words = "+".join(f"word{index}" for index in range(30))
    with CaptureQueriesContext(connection) as captured:
        assert APIClient().get(f"/api/v1/books/?search={words}").status_code == 200
    likes = max(query["sql"].upper().count(" LIKE ") for query in captured.captured_queries)
    assert likes == 5 * 2  # five words, each in the books' two search fields (title, subject's name)


def test_a_products_reviews_are_its_newest_with_the_average_and_count_of_all(monkeypatch):
    product = ProductFactory(slug="physics")
    for rating in (5, 4, 3):
        Review.objects.create(product=product, user=UserFactory(), rating=rating, status=Review.Status.APPROVED)
    monkeypatch.setattr(shop_api, "REVIEWS_SHOWN", 2)
    data = APIClient().get("/api/v1/products/physics/reviews/").json()
    assert data["count"] == 3 and float(data["average"]) == 4.0
    assert [review["rating"] for review in data["results"]] == [3, 4]  # the newest two
