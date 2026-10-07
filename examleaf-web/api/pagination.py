from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    """?page=2&page_size=100: 50 a page unless asked, never more than 200."""

    page_size_query_param = "page_size"
    max_page_size = 200
