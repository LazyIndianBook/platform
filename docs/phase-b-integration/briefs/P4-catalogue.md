# Package P4: Catalogue (model: Claude Opus 5.5)

Ports: Django 8114, console 3034 (`E2E_API_PORT=8114 E2E_WEB_PORT=3034`), the public site's dev server 3044 if you
run it. Read COMMON.md first. Your worktree is a checkout of the `phase-b` integration branch, which already holds
batch A: Tax added `Product.hsn` (a foreign key to the HSN master), `tax_treatment`, `tax_note` and `tax_problem`
and the master's API under `/api/v1/staff/tax/hsn/`; Content added `content/isbn.py` (ISBN-13 validation) and
`content/latex.py`; Orders, Support, Legal and privacy, Staff, Settings and System are there too. Read
`examleaf-web/CHANGELOG.md`'s Phase B entries and API.md's Tax and Content sections before building, and reuse them.

Plan rows: section 5.5 (every row marked **must**), 5.0, section 7.7's Product (weight, dimensions, edition is
should: skip), CouponCode and History rows, 5.13's coupons and offers row (approval above the discount threshold) and
the dark-pattern rules of section 5.5, section 9's date (1 January 2027: the prior price), section 10.1 ("No price
manipulation… different prices only through published channels": a rule written into the docs and the coupon
validation). Research: `research-commerce-gst.md` 2 and 6, `research-lms-crm-cms.md` 0, 3.5 and 6.3,
`inventory.md` 3, 3.9, 11.3.

## What exists (read before building)

`shop/models.py` (Product with kinds, `mrp`, `price`, `stock`, `weight` defaulting to 0, `isbn`, SEO fields, pictures
through django-pictures, BundleItem, Category as an MP_Node tree, Collection and CollectionItem, ProductType,
Attribute and AttributeValue, Coupon, Offer with `combinable`, ShippingRate, StockAlert, SlugHistory), `shop/admin.py`
(the admin's product form, import-export resources, the logged exports), `shop/cart.py` and `api/shop.py` (the
storefront's product serializer, the saving, the cart's coupon and offer application, the "only N left" and the
breakup), `staff/approvals.py` (`Price`, `Coupon`: `product.price` and `coupon.create`), `shop/tasks.py` (the hourly
stock-alert email, the low-stock report), `shop/test_catalogue.py`, `shop/test_offers.py`, `shop/test_offer_limits.py`,
the website's product page (`examleaf-frontend/src/app/(shop)/shop/[slug]/`), RUNBOOK "Coupons", "Offers",
"Categories, collections, attributes", "Stock, stock alerts and the low-stock email".

## Backend: `shop/staff_catalogue.py`, mounted at `/api/v1/staff/catalogue/` (tag "catalogue (staff)"), `shop/barcode.py` (EAN-13)

1. **Products**: `GET catalogue/products/` (cursor pages; filters kind, category, collection, published, stock
   state, `tax_problem`, `q`), `GET catalogue/products/{slug}/` (every field the admin edits, grouped by section in the
   serializer's documentation: identity, prices, tax (read from Tax's fields: the HSN, the treatment, the rate the
   master gives today and the next scheduled change), physical (weight, dimensions, packaging), stock, pictures,
   bundle lines, SEO), `PATCH catalogue/products/{slug}/` (`shop.change_product`; a price change goes through
   `approvals.ask("product.price", …)` as the admin does today and answers 202 above the discount limit; the other
   fields save at once; history written), `POST catalogue/products/` (`shop.add_product`), pictures through
   `POST catalogue/products/{slug}/pictures/` (multipart, the same storage and sizes as the admin), bundle lines
   `PUT catalogue/products/{slug}/bundle/` (components and quantities; a bundle takes stock from its components:
   verify the existing reservation does and test it). **Weight and dimensions**: physical products need a non-zero
   weight (grams) and either dimensions (length, width, height in cm) or a `packaging` kind (flyer by default) for the
   courier quote (`shipping` reads `weight`: check and keep its reading); a validation error otherwise; a data
   migration sets `packaging=flyer` on existing physical products and leaves weight 0 to be fixed, listed by
   `GET catalogue/products/?incomplete=1` and a card on the module's home.
2. **History and the prior price**: `simple_history` on Product, Coupon, Offer and ShippingRate (migrations with
   `populate_history`-style initial rows: a data migration creating one historical row per existing object), `GET
   catalogue/products/{slug}/history/` (field, before, after, who, when) and the same for coupons, offers and rates.
   `shop.pricing.prior_price(product, on=today)`: the lowest selling price in the 30 days before the current price's
   effective date (from the history rows), returned when the current price is lower; the rule applies from
   `SHOP_PRIOR_PRICE_FROM` (default 2027-01-01) and the storefront's product serializer gains `prior_price` (null
   before the date or when not reduced); `GET catalogue/products/{slug}/prior-price/?price=` answers the effect of a
   proposed price before saving. The website's product page shows "Lowest price in the 30 days before this reduction:
   ₹X" beside a reduced price when the API gives one (Answer Script design; one line; Vitest).
3. **Coupons**: `GET/POST catalogue/coupons/`, `GET/PATCH catalogue/coupons/{code}/` (through `approvals.Coupon` for
   create as today; an edit that deepens the discount beyond the maker's limit through the same rule: extend the
   action with an `update` path or a `coupon.change` action), rules as the model has them (percent or fixed, minimum
   order, dates, maximum uses, per customer, products and categories in or out: add `include_products`,
   `include_categories`, `exclude_products`, `exclude_categories` and `first_order_only` and `stackable` fields if
   missing, honoured by the cart), **bulk single-use codes per school**: `shop.CouponCode` (coupon, code, used by, used
   at) generated by a job (`Job.Kind.COUPON_CODES`: count, a prefix, the school's name as the coupon's note; the result
   file a CSV of the codes for the school, downloadable by the starter), the cart's coupon application accepting a
   single-use code (marks it used in the order's transaction; a used code refused; a cancelled order releases it), the
   storefront unchanged in shape.
4. **Offers**: `GET/POST/PATCH catalogue/offers/` (dates, scope, `combinable`, approval above the discount limit
   through a `offer.create` action modelled on `Coupon`'s), **the dark-pattern guardrails as validation**: a countdown
   only with a real end date (`show_countdown` requires `ends_at`); "only N left" only from real stock (the
   storefront's low-stock line reads `stock` and a threshold, never a typed number: verify and test); no pre-ticked
   add-ons (a test that the cart API adds nothing the customer did not ask for); every fee shown before checkout (the
   cart's breakup carries shipping and the COD fee: test); no guilt-trip copy: `shop.copy_rules.check(text)` refuses
   the phrases of `SHOP_DARK_PATTERN_PHRASES` (a setting with a default list from the 2023 guidelines' examples:
   "only fools", "don't miss", "last chance", "hurry", "you will regret", "limited time" without a date, case-
   insensitive) in offer names, coupon descriptions and banners with a message naming the pattern; the 13 patterns
   listed in the docs. The founder's rule "no price discrimination between consumers of the same class" written into
   the catalogue README and enforced as: a coupon or offer may not target an account or a list of accounts (there is no
   such field: keep it so, with a test that the serializers have none).
5. **Shipping rates**: `GET/POST/PATCH catalogue/shipping-rates/` with history; the free-shipping threshold and the
   COD fee shown before checkout (exists: test).
6. **ISBN and barcodes**: `content.isbn.validate` on the product's `isbn` (checksum, one per format: unique among
   products of the same `kind`), `GET catalogue/products/{slug}/barcode.svg` (EAN-13 drawn by `shop/barcode.py`
   from the standard's L, G and R patterns, tested against a known encoding, no new dependency) for the printer and
   the packing slip.
7. **Stock**: `GET catalogue/stock-alerts/` (back-in-stock requests per product: counts and the last ask; the hourly
   email exists), `GET catalogue/stock/` (levels with the low-stock threshold and the reserved count; `set_stock`
   through `POST catalogue/products/{slug}/stock/` with a reason, audited; ERPNext's stock comes in Phase C).
8. **Categories, collections, types and attributes**: list and edit endpoints with explicit serializers
   (`shop.change_category` and so on; the tree moves for categories through treebeard's methods), slugs renamed keep
   `SlugHistory` (exists: test through the API).
9. **Import and export** as jobs with a preview: `Job.Kind.PRODUCT_IMPORT` (`shop.import_product`: a CSV in the
   format `shop/admin.py`'s resource exports; a dry run answering created, updated, unchanged and errors per row, then
   Apply with the same file; history written), `Job.Kind.PRODUCT_EXPORT` (`shop.export_product`; the current filter;
   capped by `export_rows` with approval above; formula cells escaped).
10. The HSN chip: the list and record carry `tax_problem` and the master's rate for today from Tax's fields; the
    product form picks the HSN from `tax/hsn/`.
11. **Sync to ERPNext**: the outbox's `item.upserted` keeps firing on the fields it watches (`erp/producers.py`:
    read which); the erp tests stay green.

Permissions: Django's verbs on the shop's catalogue models (exist in the roles), `shop.import_product` and
`shop.export_product` (exist), `staff.approve_discount` (exists), `shop.view_couponcode` by rule; SALES edits prices
and stock, CONTENT_EDITOR product pages and SEO, MARKETING coupons and offers, FINANCE tax fields and approvals.

## Tests the exit criteria need

The prior price from a price-history fixture (a price of 300 for 40 days, 250 for 10 days, then 200: the prior price
is 250; before the setting's date null; not reduced: null); the weight validation and the migration's `incomplete`
list; every endpoint in the matrix; the single-use code used once and released by a cancellation; the price change
above the limit answering 202 and the edit within it saving; the offer refused without an end date when it shows a
countdown; the phrase check; no account targeting; the EAN-13 encoding; the ISBN uniqueness per kind; the import dry
run and apply on a fixture CSV; the export cap; query counts; the storefront's `prior_price` field.

## Console

`/catalogue/` (home: products incomplete for the courier, tax problems, low stock, back-in-stock requests),
`/catalogue/products/` (the list with the chips), `/catalogue/products/[slug]/` (sections with the save bar; the tax
panel shows today's rate and the next change; editing a price shows the prior-price rule's effect before saving and
the 202 notice), `/catalogue/products/new/`, `/catalogue/coupons/` and `[code]/` (bulk codes job with the file),
`/catalogue/offers/` and `[id]/`, `/catalogue/shipping-rates/`, `/catalogue/categories/` (the tree with move),
`/catalogue/collections/`, `/catalogue/stock/`, `/catalogue/import/` (upload, dry run, apply with `JobProgress`),
history on each record. Mock fixtures for every state. Mock journey: products → a product → a price edit with the
prior-price note → 202; coupons → bulk codes job. Real journey (`real.spec.ts` + seed): SALES edits a product's
weight and sees it leave the incomplete list.

## Boundaries

The HSN master, tax treatments and the series are Tax's (read their fields; the master's API exists); orders and
stock reservation are Orders'; Marketing's campaigns are Phase D. Do not edit `staff/api.py`.
