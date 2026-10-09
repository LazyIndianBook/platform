from rest_framework.filters import SearchFilter


class BoundedSearchFilter(SearchFilter):
    """DRF's ?search=, bounded (REST_FRAMEWORK's DEFAULT_FILTER_BACKENDS): the first MAX_TERMS words, each cut to
    MAX_LENGTH characters. DRF makes a LIKE clause of every word for every search field, so an address of a thousand
    words was a query of thousands of clauses, run against the database by anyone, and a cache entry of its own."""

    MAX_TERMS, MAX_LENGTH = 5, 50

    def get_search_terms(self, request):
        return [term[: self.MAX_LENGTH] for term in super().get_search_terms(request)[: self.MAX_TERMS]]
