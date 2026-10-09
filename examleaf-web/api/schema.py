"""The OpenAPI schema's operations, tagged by area (SPECTACULAR_SETTINGS["TAGS"] describes the areas). A module of its
own: the views' decorators load DEFAULT_SCHEMA_CLASS while api.views is being imported."""

from drf_spectacular import openapi

AREAS = {  # the first part of the path (after /api/v1/), by area; "auth" and "learn" are areas already
    **dict.fromkeys(["me", "devices"], "account"),
    **dict.fromkeys(["boards", "subjects", "books", "papers", "qr", "reports", "errata"], "catalogue"),
    "attempts": "record",
    **dict.fromkeys(["products", "categories", "collections", "cart", "addresses", "orders", "quotes"], "shop"),
    **dict.fromkeys(["config", "pages"], "site"),
}


class AutoSchema(openapi.AutoSchema):
    def get_tags(self):
        return [AREAS.get(tag, tag) for tag in super().get_tags()]
