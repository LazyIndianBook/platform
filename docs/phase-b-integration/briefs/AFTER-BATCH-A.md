# Integration notes after batch A (read after COMMON.md and your package file)

Batch A is merged on `phase-b`, your worktree's base: Orders (`shop/staff_orders.py`, `shop/order_jobs.py`), Tax
(`shop/tax.py`, `shop/staff_tax.py`, `shop/gstr1.py`), Content (`content/staff_api.py`, `content/review.py`,
`content/reports.py`, `content/imports.py`, `content/isbn.py`, `content/latex.py`), Support (`support/`), Legal and
privacy (`staff/privacy_api.py`, `staff/compliance.py`, `examleaf/retention.py`, `accounts/audiences.py`), Staff,
Settings and System (`staff/api.py`, `staff/services.py`, `staff/system_api.py`, `integrations/api.py`,
`integrations/connections.py`, `ops/staff_api.py`). Read `examleaf-web/CHANGELOG.md`'s six Phase B entries and the
Phase B sections of `examleaf-web/API.md` before building; reuse what they added.

Rules the merges taught, which the tests now enforce:

1. **Schema component names are global.** drf-spectacular names a component after its serializer class, across every
   app: two classes named `ClockSerializer` or `CancelSerializer` in different apps break the schema and three tests
   (`api/tests.py`, `erp/tests/test_api.py`, `shipping/tests/test_api.py`). Prefix every serializer of your module
   with its name (`FinancePaymentSerializer`, `CatalogueProductSerializer`, `CourseClipSerializer`, …), and check with
   `$PY manage.py spectacular --validate --fail-on-warn --file /dev/null`.
2. **One enum name per choice set.** `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` may not give two names to the same
   values (an `Enum naming` error): before adding an override, grep the existing ones (`settings.py`) for the same
   values. Existing shared names: `ChannelEnum` (a data request's), `MessageChannelEnum` (email, sms, whatsapp),
   `LanguageEnum` (as, bn, en), `TicketContactEnum` (email, nch, phone, whatsapp), `StateEnum` (the Indian states),
   `ProductKindEnum`, `RoleEnum`.
3. **Jobs.** `staff/serializers.py` `JobStartSerializer.validate`: each kind's branch sets `data["params"]` and
   `return data` (the generic bulk validation follows and refuses anything else); `staff/jobs.py`: `permission()`
   is a chain ending in `order_jobs.PERMISSIONS.get(kind)`; `LIMITS` and `RUNNERS` are dicts you add to.
4. **`staff/urls.py`**: the modules' includes are one block in the order of their paths (connections, content,
   orders, support, system, tax, templates): add yours in that order.
5. **Settings registry** (`staff/config.py`): `Spec(kind, label, permission, default, group=…, max_length=…,
   validate=…)`; `group` is the Settings page's section (`shop`, `tax`, `support`, `erp`, `disclosures`, …).
6. **Migrations**: `staff` is at `0017`; name yours `00NN_phase_b_<module>.py` with the next number; a merge
   migration is made at integration if two of you add one.
7. **The console mock**: `src/mocks/staff/handler.ts` lends each module a kit (`ordersKit`, `toolsOf`, `KIT`): add
   yours the same way in your own file (`src/mocks/staff/<module>.ts`) and one `case` per permission map and route
   switch; new job kinds join the one `case "jobs"` block and the job file answers.
8. **New console dependencies** (the Content package added `katex`): after `npm install` in your worktree, say so in
   your report; the integration runs `npm install` once more.
9. **Playwright**: delete `examleaf-admin/.next` before a run and never edit files during one (Next's dev server
   otherwise reloads the sign-in page in a loop); start Playwright's servers on your package's ports.
10. **`forget_orders(orders, today=None)`** and `held_orders(ids, today)`: pass the day you simulate.
11. **Tests that create privileged staff (OWNER, ADMIN, FINANCE)** need a passkey row (`accounts/factories.py`
    adds one; `e2e/django.ts` too), else the staff API answers 403 `passkey_required`.
12. Every lookup of a person by name, email or phone writes `customer.lookup` with a keyed hash (Orders'
    `shop/staff_orders.py` has the helper `lookup_event`; reuse it).
