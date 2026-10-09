# Sources: couriers and integrations research

Fetched on 9 October 2026 unless a line says otherwise. Quality notes: "official" is the vendor's or government's own
page; "integrator" is a third party that integrates the vendor; "news", "blog", "review site" as stated. Numbers 1
to 99 cover couriers and design patterns; 200 to 299 payments and messaging; 300 to 399 accounting, tax and
government; 400 to 499 operations tooling and integration UI patterns.

## Shiprocket
- [1] https://apidocs.shiprocket.in/ (the published Postman collection, read in full as JSON from https://documenter.gw.postman.com/api/collections/8407119/SzYW1zB2?segregateAuth=true&versionTag=latest) — fetched 2026-10-09 — official API reference: every endpoint, parameters, examples, status-code tables, webhook spec; the HTML site itself answered 502.
- [2] https://support.shiprocket.in/support/solutions/articles/43000337456-shiprocket-api-document-helpsheet — fetched 2026-10-09 — official help; base URL, token validity 240 hours, main endpoints.
- [3] https://www.shiprocket.in/pricing/ — fetched 2026-10-09 — official pricing page; plan fees, average shipment cost, refund thresholds; rate cards behind a link not captured.
- [4] https://support.shiprocket.in/support/solutions/articles/152000000250-what-are-the-available-plans-in-shiprocket-and-which-one-would-be-the-most-suitable-for-my-shipping-n — fetched 2026-10-09 — official help, modified 28 Nov 2023; outdated plans, kept for the per-0.5 kg rates it quotes.
- [5] https://support.shiprocket.in/support/solutions/articles/43000463560 — fetched 2026-10-09 — official help, modified 24 Jun 2024; COD remittance D+8, Mon/Wed/Fri.
- [6] https://shiprocket.in/blog/early-cod-by-shiprocket — fetched 2026-10-09 — Shiprocket's own blog; Early COD plans and fees (GST included); not a contract.
- [7] https://support.shiprocket.in/support/solutions/articles/152000000970-instant-cod-faqs — fetched 2026-10-09 — official help, modified 22 Oct 2024.
- [8] https://www.shiprocket.in/knowledgebase/weight-dispute-manager — fetched 2026-10-09 — official knowledge base, marked "Last Updated: 8 years ago"; the dispute rules still match [9][10].
- [9] https://support.shiprocket.in/support/solutions/articles/43000604038-how-long-does-it-take-to-resolve-my-order-weight-dispute- — fetched 2026-10-09 — official help, 2020.
- [10] https://support.shiprocket.in/support/solutions/articles/43000662858-important-terms-all-shiprocket-users-should-know — fetched 2026-10-09 — official help, Apr 2022; status, NDR, RTO, weight and return glossary.
- [11] https://support.shiprocket.in/support/solutions/articles/43000614621-explaining-shiprocket-passbook-charges — fetched 2026-10-09 — official help; wallet charge types.
- [12] https://support.shiprocket.in/support/solutions/articles/152000000168-how-to-check-the-applied-cod-charges- — fetched 2026-10-09 — official help; COD fee rule and example.
- [13] https://www.shiprocket.in/engage360/terms-and-conditions — fetched 2026-10-09 — official terms; Engage 360 pricing model, WhatsApp number exclusivity, Kaleyra.
- [14] https://shiprocket.in/blog/key-features-of-shiprocket-engage — fetched 2026-10-09 — Shiprocket's own blog; feature list only.
- [15] https://support.shiprocket.in/support/solutions/articles/43000664184-explaining-shipping-zones-how-shipment-zones-affect-order-fulfillment-and-rates- — fetched 2026-10-09 — official help, Dec 2022; zone definitions.
- [16] https://support.shiprocket.in/support/solutions/articles/152000000877-fastrr-checkout-guide-an-overview-of-dashboard — fetched 2026-10-09 — official help, modified 27 Jul 2026; Fastrr Checkout features.
- [17] https://www.itln.in/e-commerce/shiprocket-inks-agreement-to-acquire-pickrr-in-a-usd-200-million-deal-1345694 — fetched 2026-10-09 — trade news, 15 Jun 2022; majority stake for US$200 million.
- [18] https://inc42.com/buzz/logistics-startup-shiprocket-picks-up-rival-pickrr-in-a-200-mn-deal/ — fetched 2026-10-09 — trade news, 15 Jun 2022; 80 % stake, Pickrr's Fastrr checkout.
- [19] https://sr-website.shiprocket.in/developers/ — fetched 2026-10-09 — official developers page; mentions "working in Sandbox" without detail.
- [20] https://support.shiprocket.in/support/solutions/articles/43000590102-how-to-block-oda-out-of-delivery-area-pincodes- — fetched 2026-10-09 — official help, Sep 2021; ODA definition and blocking.
- [21] https://au.trustpilot.com/review/www.shiprocket.in?page=4 — fetched 2026-10-09 — review site; 1.2/5 over 2,163 reviews, July–August 2026 complaints; anecdotal and self-selected.

## Delhivery
- [30] https://delhivery-express-api-doc.readme.io/llms.txt — fetched 2026-10-09 — official last-mile API reference (index); older public docs, the current ones are inside Delhivery One [46].
- [31] https://delhivery-express-api-doc.readme.io/reference/best-practises-to-follow-the-api-documentation — fetched 2026-10-09 — official; `Authorization: Token`, staging vs production hosts, per-environment tokens.
- [32] https://delhivery-express-api-doc.readme.io/reference/must-to-have-for-integration — fetched 2026-10-09 — official; test and production tokens, warehouses.
- [33] https://delhivery-express-api-doc.readme.io/reference/order-creation-api — fetched 2026-10-09 — official; create.json rules, GST fields, e-way bill above ₹50,000.
- [34] https://delhivery-express-api-doc.readme.io/reference/order-tracking-api — fetched 2026-10-09 — official; 750 requests per 5 minutes per IP.
- [35] https://delhivery-express-api-doc.readme.io/reference/tracking-via-push-api-webhook-1 — fetched 2026-10-09 — official; push set-up and sample scan.
- [36] https://delhivery-express-api-doc.readme.io/reference/cancel-order-api — fetched 2026-10-09 — official.
- [37] https://delhivery-express-api-doc.readme.io/reference/asynchronous-ndr-package-action-api — fetched 2026-10-09 — official; NDR actions and limits.
- [38] https://delhivery-express-api-doc.readme.io/reference/pickup-request-creation-api — fetched 2026-10-09 — official.
- [39] https://delhivery-express-api-doc.readme.io/reference/packing-slip-api — fetched 2026-10-09 — official.
- [40] https://delhivery-express-api-doc.readme.io/reference/invoice-shipping-charge-api — fetched 2026-10-09 — official; 40 requests a minute.
- [41] https://delhivery-express-api-doc.readme.io/reference/bulk-waybill — fetched 2026-10-09 — official; waybill limits.
- [42] https://delhivery-express-api-doc.readme.io/reference/prepaid-and-cod-shipments — fetched 2026-10-09 — official; status types.
- [43] https://delhivery-express-api-doc.readme.io/reference/1-pincode-servicability-api — fetched 2026-10-09 — official.
- [44] https://delhivery-express-api-doc.readme.io/reference/frequently-asked-questions — fetched 2026-10-09 — official; common errors.
- [45] https://help.delhivery.com/docs/api-token-generation — fetched 2026-10-09 — official help, Nov 2023; token regeneration.
- [46] https://help.delhivery.com/docs/client-developer-portal-1 — fetched 2026-10-09 — official help, Aug 2023; developer portal and staging.
- [47] https://help.delhivery.com/docs/cod-remittance — fetched 2026-10-09 — official help; 48-hour remittance.
- [48] https://help.delhivery.com/docs/rate-card — fetched 2026-10-09 — official help; zones A to F, surcharges.
- [49] https://help.delhivery.com/docs/weight-dispute — fetched 2026-10-09 — official help; flyers, claims.
- [50] https://help.delhivery.com/docs/smartndr — fetched 2026-10-09 — official help; SmartNDR.
- [51] https://www.itln.in/logistics/delhivery-launches-digtial-shipping-platform-for-smes-delhivery-one-1349549 — fetched 2026-10-09 — trade news, Aug 2023; Delhivery One launch terms.
- [52] https://github.com/nguyendachuy/laravel-delhivery-api — fetched 2026-10-09 — third-party SDK source; endpoint paths for warehouses and NDR status.
- [53] https://nsearchives.nseindia.com/corporate/DELHIVERYLTD_17062025205312_Intimation_CCI_Approval_Final_Signed.pdf — fetched 2026-10-09 — stock-exchange filing, 17 Jun 2025; CCI approval of the Ecom Express acquisition.

## India Post
- [60] https://www.indiapost.gov.in/mailproducts/domesticservices/domestictariff — fetched 2026-10-09 — official tariff page (site updated 12 Aug 2026); Book Post and the first two Gyan Post slabs.
- [61] https://www.indiapost.gov.in/mailproducts/domesticservices/bookpost — fetched 2026-10-09 — official; Book Post conditions under the Post Office Regulations, 2024.
- [62] https://www.indiapost.gov.in/mailproducts/domesticservices/gyanpost — fetched 2026-10-09 — official; Gyan Post eligibility and conditions.
- [63] https://www.staffnews.in/2025/04/post-office-second-amendment-regulations-2025.html — fetched 2026-10-09 — blog reproducing G.S.R. 263(E) of 28 Apr 2025 (Regulation 92A and the full Gyan Post tariff); check against the e-Gazette before relying on it.
- [64] https://www.newsonair.gov.in/gyan-post-introduced-by-dept-of-posts-to-deliver-educational-books-at-affordable-rates — fetched 2026-10-09 — government broadcaster news, Jun 2025.
- [65] https://www.newsonair.gov.in/department-of-posts-revises-inland-speed-post-document-tariff-introduces-new-features — fetched 2026-10-09 — government broadcaster news, 27 Sep 2025; Speed Post document tariff from 1 Oct 2025, registration add-on.
- [66] https://www.tribuneindia.com/news/india/speed-post-now-basic-mail-service-govt-revises-tariffs-effective-october-1 — fetched 2026-10-09 — newspaper; gives per-50 g rates that conflict with [65].
- [67] https://www.scconline.com/blog/post/2025/08/05/india-post-to-discontinue-registered-post-september-1/ — fetched 2026-10-09 — legal news blog; Registered Post merged into Speed Post from 1 Sep 2025.
- [68] https://theprint.in/economy/india-post-defines-document-parcel-notifies-new-speed-service-rate-for-bulk-customers/2998285/ — fetched 2026-10-09 — news, 27 Jul 2026; document vs parcel, 24/48 Speed Post in six cities.
- [69] https://upstox.com/news/business-news/latest-updates/govt-clarifies-what-qualifies-as-postal-document-parcel-new-speed-post-tariffs-from-aug-1/article-197657/ — fetched 2026-10-09 — news, 28 Jul 2026; 24/48 Speed Post rates from 1 Aug 2026.
- [70] https://utilities.cept.gov.in/dop/pdfbind.ashx?id=5778 — fetched 2026-10-09 — official (CEPT): the SOP for onboarding e-commerce customers and "DoP Integration with Bulk Customers" v6.1 of 21 May 2021; may predate the 2025 software change.
- [71] https://postandparcel.info/?p=159773 — fetched 2026-10-09 — trade news, Aug 2025; national APT rollout across 1.64 lakh post offices.
- [72] https://www.taxheal.com/india-post-to-take-e-commerce-to-every-indian.html — fetched 2026-10-09 — tax site reproducing a PIB release of 28 Jan 2016; India Post COD for e-commerce.

## Other aggregators and couriers
- [80] https://nimbuspost.com/pricing — fetched 2026-10-09 — official pricing page; "starts at" rates per 500 g by volume tier.
- [81] https://docs.ithinklogistics.com/doc-sync-order/2 — fetched 2026-10-09 — official API doc; auth fields, pre-alpha host, 25 orders per call.
- [82] https://shipway.in/documentation/ — fetched 2026-10-09 — official page; APIs on request.
- [83] https://developer.dhl.com/api-reference/bd-waybill — fetched 2026-10-09 — official (Blue Dart APIs on DHL's developer portal); JWT, licence key and login id.
- [84] https://support.aftership.com/en/articles/15380680-dtdc-developer-guide-and-api-credentials — fetched 2026-10-09 — integrator doc; DTDC credentials, sandbox.
- [85] https://docs.clickpost.ai/docs/xpressbees-b2c-sps — fetched 2026-10-09 — integrator doc; Xpressbees credentials and features.
- [86] https://www.icarry.in/icarry-rate-chart.pdf — fetched 2026-10-09 — an aggregator's public B2C rate chart "Updated Oct 2, 2026", GST included; one data point, rates vary by account and aggregator.
- [87] https://www.clickpost.ai/blog/top-10-best-cod-cash-on-delivery-courier-services-companies — fetched 2026-10-09 — vendor blog, updated 22 Sep 2026; network sizes and India Post remittance window; low reliability (it also claims "19,000+ post offices").
- [88] https://base.com/en-EN/help/knowledgebase/nimbuspost/ — fetched 2026-10-09 — integrator guide; NimbusPost API key and secret.

## Design patterns
- [90] https://docs.celeryq.dev/en/stable/userguide/tasks.html — fetched 2026-10-09 — official Celery docs; autoretry, backoff, jitter, acks_late, idempotency.
- [91] https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker — fetched 2026-10-09 — official architecture guidance (updated Sep 2026); states, manual override, journal and replay.
- [92] https://cryptography.io/en/latest/fernet/ — fetched 2026-10-09 — official library docs; MultiFernet and rotate().
- [93] https://api.17track.net/en/doc?version=v2.2 — fetched 2026-10-09 — official 17TRACK API docs (now v2.4 paths); auth header, limits, free quota.

## Payments and messaging (200 to 299)

### Razorpay
- [200] https://razorpay.com/docs/build/llm-docs/api/authentication.md — fetched 2026-10-09 — official doc
- [201] https://razorpay.com/docs/build/llm-docs/api/understand.md — fetched 2026-10-09 — official doc (rate limiting, pagination)
- [202] https://razorpay.com/docs/build/llm-docs/webhooks.md — fetched 2026-10-09 — official doc
- [203] https://razorpay.com/docs/build/llm-docs/webhooks/validate-test.md — fetched 2026-10-09 — official doc (signature, idempotency)
- [204] https://razorpay.com/docs/build/llm-docs/webhooks/best-practices.md — fetched 2026-10-09 — official doc (retries, disable)
- [205] https://razorpay.com/docs/build/llm-docs/webhooks/faqs.md — fetched 2026-10-09 — official doc
- [206] https://razorpay.com/docs/build/llm-docs/webhooks/setup-edit-payments.md — fetched 2026-10-09 — official doc
- [207] https://razorpay.com/docs/build/llm-docs/webhooks/all.md — fetched 2026-10-09 — official doc (event list)
- [208] https://razorpay.com/docs/build/llm-docs/security/whitelists.md — fetched 2026-10-09 — official doc (IPs)
- [209] https://razorpay.com/docs/build/llm-docs/webhooks/payments.md — fetched 2026-10-09 — official doc (payload envelope)
- [210] https://razorpay.com/docs/build/llm-docs/webhooks/settlements.md — fetched 2026-10-09 — official doc
- [211] https://razorpay.com/docs/build/llm-docs/webhooks/smart-collect.md — fetched 2026-10-09 — official doc
- [212] https://razorpay.com/docs/build/llm-docs/api/orders/entity.md — fetched 2026-10-09 — official API reference
- [213] https://razorpay.com/docs/build/llm-docs/payments/payments/capture-settings.md — fetched 2026-10-09 — official doc
- [214] https://razorpay.com/docs/build/llm-docs/api/refunds.md — fetched 2026-10-09 — official API reference
- [215] https://razorpay.com/docs/build/llm-docs/api/refunds/normal-refunds-idempotent.md — fetched 2026-10-09 — official API reference
- [216] https://razorpay.com/docs/build/llm-docs/payments/refunds.md — fetched 2026-10-09 — official doc
- [217] https://razorpay.com/docs/build/llm-docs/payments/refunds/instant.md — fetched 2026-10-09 — official doc
- [218] https://razorpay.com/docs/build/llm-docs/payments/refunds/normal.md — fetched 2026-10-09 — official doc (internally inconsistent timing)
- [220] https://razorpay.com/docs/build/llm-docs/api/settlements.md — fetched 2026-10-09 — official API reference
- [221] https://razorpay.com/docs/build/llm-docs/api/settlements/fetch-recon.md — fetched 2026-10-09 — official API reference
- [222] https://razorpay.com/docs/build/llm-docs/api/settlements/instant.md — fetched 2026-10-09 — official API reference
- [223] https://razorpay.com/docs/build/llm-docs/payments/settlements/instant.md — fetched 2026-10-09 — official doc
- [224] https://razorpay.com/docs/build/llm-docs/payments/settlements/faqs.md — fetched 2026-10-09 — official doc
- [225] https://razorpay.com/docs/build/llm-docs/payments/dashboard/reports.md — fetched 2026-10-09 — official doc
- [226] https://razorpay.com/capital/instant-settlements/ — fetched 2026-10-09 — official product/pricing page (GST not stated)
- [227] https://razorpay.com/pricing.md — fetched 2026-10-09 — official machine-readable rate card served at razorpay.com/pricing/ to non-browser clients, "Last updated: May 2026"
- [228] https://razorpay.com/docs/build/llm-docs/api/payments/payment-links/create-standard.md — fetched 2026-10-09 — official API reference
- [229] https://razorpay.com/docs/build/llm-docs/payments/payment-links/apis.md — fetched 2026-10-09 — official doc (callback, signature)
- [230] https://razorpay.com/docs/build/llm-docs/payments/payment-links/reminders.md — fetched 2026-10-09 — official doc
- [231] https://razorpay.com/docs/build/llm-docs/payments/payment-links/states.md — fetched 2026-10-09 — official doc
- [232] https://razorpay.com/docs/build/llm-docs/payments/payment-links/bank-transfer.md — fetched 2026-10-09 — official doc
- [233] https://razorpay.com/docs/build/llm-docs/payments/smart-collect.md — fetched 2026-10-09 — official doc
- [234] https://razorpay.com/docs/build/llm-docs/api/payments/smart-collect.md — fetched 2026-10-09 — official API reference
- [235] https://razorpay.com/docs/build/llm-docs/payments/smart-collect/faqs.md — fetched 2026-10-09 — official doc
- [237] https://razorpay.com/docs/build/llm-docs/api/disputes.md — fetched 2026-10-09 — official API reference
- [238] https://razorpay.com/docs/build/llm-docs/api/disputes/entity.md — fetched 2026-10-09 — official API reference
- [239] https://razorpay.com/docs/build/llm-docs/payments/payments/test-card-details.md — fetched 2026-10-09 — official doc
- [240] https://razorpay.com/docs/build/llm-docs/payments/payments/test-upi-details.md — fetched 2026-10-09 — official doc
- [241] https://razorpay.com/docs/build/llm-docs/payments/dashboard/account-settings/manage-team.md — fetched 2026-10-09 — official doc (roles); API key FAQ from …/account-settings/api-keys.md

### WhatsApp: Meta and providers
- [242] https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing — fetched 2026-10-09 — official doc (rate cards "effective July 1, 2026")
- [243] https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages — fetched 2026-10-09 — official doc ("upcoming" Oct 1, 2026 charges)
- [244] https://whatsappbusiness.com/wp-json/wab/v1/pricing?market=IN&currency=INR&category=Marketing (also Utility, Authentication, Authentication International, Service, and USD) — fetched 2026-10-09 — official Meta pricing-calculator backend of business.whatsapp.com/products/platform-pricing
- [246] https://developers.facebook.com/docs/whatsapp/messaging-limits — fetched 2026-10-09 — official doc
- [247] https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization — fetched 2026-10-09 — official doc
- [248] https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review — fetched 2026-10-09 — official doc
- [249] https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-quality — fetched 2026-10-09 — official doc
- [250] https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in — fetched 2026-10-09 — official doc
- [251] https://business.whatsapp.com/policy — fetched 2026-10-09 — official policy ("Last updated: September 23, 2026")
- [252] https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint — fetched 2026-10-09 — official doc
- [253] https://msg91.com/in/pricing/whatsapp — fetched 2026-10-09 — official vendor pricing page (rate card behind a JS button, not captured)
- [254] https://msg91.com/_next/static/chunks/295198652cd5c304.js — fetched 2026-10-09 — MSG91 site bundle with its comparison data ("Zero margin on Meta pricing"); vendor marketing claim
- [255] https://docs.msg91.com/whatsapp/template-bulk — fetched 2026-10-09 — official vendor API doc (from embedded page data)
- [256] https://msg91.com/help/webhook-new/how-to-receive-whatsapp-delivery-reports-via-webhook-new — fetched 2026-10-09 — official vendor help doc
- [257] https://www.interakt.shop/pricing/ — fetched 2026-10-09 — official vendor pricing page (partly stale wording on service messages)
- [258] https://www.gupshup.io/channels/self-serve/whatsapp/pricing — fetched 2026-10-09 — official vendor pricing page
- [259] https://live-mt-server.wati.io/wati/api/v1/pricing/getPlansByGeo?countryCode=IN — fetched 2026-10-09 — Wati's own plan API used by wati.io/pricing (prices in paise)
- [260] https://drive.google.com/file/d/1BzsDt0bQYqxBMTwQyxcq_KZCfc4AD3sE/view — fetched 2026-10-09 — Wati INR Growth rate card PDF dated October 1, 2026, linked from wati.io/pricing

### SMS: TRAI DLT and MSG91
- [261] https://www.trai.gov.in/sites/default/files/2026-05/CA_21052026.pdf — fetched 2026-10-09 — official TRAI consolidated TCCCPR text (gazette text prevails)
- [262] https://trai.gov.in/sites/default/files/2025-02/Regulation_12022025_0.pdf — fetched 2026-10-09 — official TCCCPR (Second Amendment) Regulations 2025
- [263] https://trai.gov.in/sites/default/files/2025-02/PR_No.11of2025.pdf — fetched 2026-10-09 — official TRAI press release (OCR typo "-F'" for "-P")
- [264] https://trai.gov.in/sites/default/files/2024-09/Direction_30082024_0.pdf — fetched 2026-10-09 — official TRAI direction (URL whitelisting from 1 Oct 2024)
- [265] https://www.trai.gov.in/sites/default/files/2025-11/Directions_18112025_0.PDF — fetched 2026-10-09 — official TRAI direction (variable pre-tagging)
- [266] https://msg91.com/help/dlt-registration-in-india/variable-tagging-on-dlt-sms-templates — fetched 2026-10-09 — vendor help doc
- [267] https://msg91.com/help/dlt-registration-in-india/dlt-content-template-faqs — fetched 2026-10-09 — vendor help doc (partly outdated)
- [268] https://msg91.com/help/dlt-registration-in-india/dlt-template-scrubbing-filtering-rules — fetched 2026-10-09 — vendor help doc
- [269] https://docs.msg91.com/sms/send-sms — fetched 2026-10-09 — official vendor API doc (Flow API)
- [270] https://docs.msg91.com/sms/add-flow — fetched 2026-10-09 — official vendor API doc (addTemplate with dlt_template_id)
- [271] https://msg91.com/in/pricing/sms — fetched 2026-10-09 — official vendor pricing page
- [272] https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new — fetched 2026-10-09 — vendor help doc
- [273] https://www.fast2sms.com/help/?p=16132 — fetched 2026-10-09 — blog by a competing SMS vendor (SE → Promotional, 10 Mar 2026)
- [274] https://developer.exotel.com/docs/sms-support/dlt-entity-registration — fetched 2026-10-09 — vendor doc (registration fee "approximately")

### Amazon SES and SNS
- [275] https://docs.aws.amazon.com/ses/latest/dg/monitor-sending-activity-using-notifications.html — fetched 2026-10-09 — official doc
- [276] https://docs.aws.amazon.com/ses/latest/dg/notification-contents.html — fetched 2026-10-09 — official doc
- [277] https://docs.aws.amazon.com/ses/latest/dg/event-publishing-retrieving-sns-contents.html — fetched 2026-10-09 — official doc
- [278] https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_EventDestination.html — fetched 2026-10-09 — official API reference
- [279] https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html — fetched 2026-10-09 — official doc
- [280] https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html — fetched 2026-10-09 — official doc
- [281] https://docs.aws.amazon.com/sns/latest/api/API_SetTopicAttributes.html — fetched 2026-10-09 — official API reference (SignatureVersion default 1)
- [282] https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html — fetched 2026-10-09 — official doc
- [283] https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html — fetched 2026-10-09 — official doc
- [284] https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_ListSuppressedDestinations.html — fetched 2026-10-09 — official API reference
- [285] https://docs.aws.amazon.com/ses/latest/dg/faqs-enforcement.html — fetched 2026-10-09 — official doc (thresholds)
- [286] https://aws.amazon.com/ses/pricing/ — fetched 2026-10-09 — official pricing page (new 2026 plans)
- [287] https://docs.aws.amazon.com/general/latest/gr/ses.html — fetched 2026-10-09 — official endpoints list
- [288] https://anymail.dev/en/stable/esps/amazon_ses/ — fetched 2026-10-09 — official library doc (Anymail 15.2)
- [289] https://raw.githubusercontent.com/anymail/django-anymail/main/anymail/webhooks/amazon_ses.py — fetched 2026-10-09 — library source (main branch)

### Google sign-in and django-allauth
- [290] https://developers.google.com/identity/openid-connect/openid-connect — fetched 2026-10-09 — official doc
- [291] https://developers.google.com/identity/siwg/security-bundle — fetched 2026-10-09 — official doc (amr/auth_time setup)
- [292] https://developers.google.com/workspace/guides/configure-oauth-consent — fetched 2026-10-09 — official doc
- [293] https://support.google.com/cloud/answer/15549945 — fetched 2026-10-09 — official help (Manage App Audience)
- [294] https://support.google.com/cloud/answer/13464323 — fetched 2026-10-09 — official help (When verification is not needed)
- [295] https://knowledge.workspace.google.com/admin/security/deploy-2-step-verification — fetched 2026-10-09 — official Google help (redirect target of support.google.com/a/answer/9176657)
- [296] https://docs.allauth.org/en/latest/socialaccount/providers/google.html — fetched 2026-10-09 — official library doc
- [297] https://raw.githubusercontent.com/pennersr/django-allauth/main/allauth/socialaccount/providers/google/views.py — fetched 2026-10-09 — library source (main branch)
- [298] https://raw.githubusercontent.com/pennersr/django-allauth/main/allauth/socialaccount/internal/flows/login.py — fetched 2026-10-09 — library source (main branch)
- [299] https://raw.githubusercontent.com/pennersr/django-allauth/main/allauth/mfa/stages.py — fetched 2026-10-09 — library source (main branch)

## Accounting, tax and government (300 to 399)

### Tally
- [300] https://help.tallysolutions.com/tallyprime/release-notes/ — fetched 2026-10-09 — official; release list and 7.1 banner
- [301] https://help.tallysolutions.com/release-notes-tallyprime-7-0/ — fetched 2026-10-09 — official; 7.0 date 19 Dec 2025, JSON data exchange
- [302] https://help.tallysolutions.com/release-notes-tallyprime-7-1/ — fetched 2026-10-09 — official; 7.1 date 20 May 2026
- [303] https://help.tallysolutions.com/release-notes-tallyprime-6/ — fetched 2026-10-09 — official; 6.0 date 24 Jan 2025
- [304] https://help.tallysolutions.com/release-notes-tallyprime-6-1/ — fetched 2026-10-09 — official; 6.1 date 16 Jun 2025
- [305] https://help.tallysolutions.com/release-notes-tallyprime-6-2/ — fetched 2026-10-09 — official; 6.2 date 18 Aug 2025
- [306] https://help.tallysolutions.com/release-notes-tally-prime-developer-7/ — fetched 2026-10-09 — official developer notes; JSON/JSONEx, Tally Connector JSON
- [307] https://help.tallysolutions.com/tally-prime-integration-using-json-1/ — fetched 2026-10-09 — official; JSON headers/body/response, TallyPrime as client
- [308] https://help.tallysolutions.com/wp-content/uploads/2025/11/Voucher-Import-Payload.docx (+ Ledger-Creation-Payload.docx, Voucher-Import-Response.docx) — fetched 2026-10-09 — official sample payloads
- [309] https://help.tallysolutions.com/xml-integration/ — fetched 2026-10-09 — official; ENVELOPE/Import Data template, port 9000
- [310] https://help.tallysolutions.com/pre-requisites-for-integrations/ — fetched 2026-10-09 — official; Data Synchronization config, HTTP headers
- [311] https://help.tallysolutions.com/?p=177881 (Scenario 2) — fetched 2026-10-09 — official; voucher XML, IMPORTRESULT/LINEERROR, Alter by MASTER ID
- [313] https://help.tallysolutions.com/nil-rated-exempt-sales-gst/ — fetched 2026-10-09 — official; exempt/nil sales and GSTR-1 8A–8D
- [314] https://help.tallysolutions.com/import-data-from-xml-json/ — fetched 2026-10-09 — official; Alt+O import, XML/Excel/JSON by release
- [315] https://help.tallysolutions.com/odbc-integrations/ — fetched 2026-10-09 — official; ODBC client/server
- [317] https://github.com/Accounting-Companion/TallyConnector — fetched 2026-10-09 — open-source README via GitHub API
- [318] https://www.nuget.org/packages/TallyConnector — fetched 2026-10-09 — NuGet registration API; versions/dates/MIT

### Zoho Books
- [320] https://www.zoho.com/books/api/v3/introduction/ — fetched 2026-10-09 — official; DCs, organization_id, rate limits
- [321] https://www.zoho.com/books/api/v3/oauth/ — fetched 2026-10-09 — official; OAuth flows, scopes, token limits
- [322] https://www.zoho.com/accounts/protocol/oauth/multi-dc.html — fetched 2026-10-09 — official; accounts.zoho.in
- [323] https://www.zoho.com/books/api/v3/invoices/ — fetched 2026-10-09 — official; India fields, e-invoice endpoints
- [324] https://www.zoho.com/books/api/v3/contacts/ — fetched 2026-10-09 — official; gst_treatment, place_of_contact
- [325] https://www.zoho.com/books/api/v3/items/ — fetched 2026-10-09 — official; is_taxable / tax_exemption_id
- [326] https://www.zoho.com/books/api/v3/credit-notes/ — fetched 2026-10-09 — official; /creditnotes
- [327] https://www.zoho.com/books/api/v3/customer-payments/ — fetched 2026-10-09 — official; /customerpayments
- [328] https://www.zoho.com/in/books/help/settings/automation/workflow-actions/webhooks.html — fetched 2026-10-09 — official; secret, HMAC, retries, timeouts
- [329] https://www.zoho.com/in/books/kb/automation/number-of-workflows.html — fetched 2026-10-09 — official KB; workflow/webhook limits (plan list looks inconsistent)
- [330] https://www.zoho.com/in/books/pricing/ — fetched 2026-10-09 — official India pricing
- [331] https://www.zoho.com/in/books/help/e-invoicing/ — fetched 2026-10-09 — official; Zoho as GSP, plans

### GST e-invoice
- [336] https://www.mahagst.gov.in/public/uploads/whatisnew/1761741007GSTN launches e-invoice registration services with private IRP’s.pdf — fetched 2026-10-09 — GSTN advisory hosted by a state tax dept; IRP URLs
- [337] https://tutorial.gst.gov.in/downloads/news/e-invoice_api_integration_guide_irps.pdf — fetched 2026-10-09 — official GSTN (as on 29 Nov 2023); free core APIs, direct-API eligibility per IRP
- [338] https://einvoice1.gst.gov.in/Others/Faqs (data: /documents/Faq*.json) — fetched 2026-10-09 — official NIC FAQs
- [339] https://einvoice1.gst.gov.in/Others/Notifications (data: /documents/Notifications.json) — fetched 2026-10-09 — official list; its 10/2023 PDF link points to an unrelated file
- [340] https://einvoice1.gst.gov.in/Notifications/notfctn-13-central-tax-english-2020.pdf — fetched 2026-10-09 — official notification text
- [341] https://einvoice1.gst.gov.in/Documents/advisory270325.pdf — fetched 2026-10-09 — official GSTN advisory; 30-day rule ≥ ₹10 cr
- [343] https://einvoice1.gst.gov.in/Others/BulkGenerationTools (+ /documents/LatestUpdates.json) — fetched 2026-10-09 — official; GePP v2.0, JSON tools, 2FA note
- [344] https://einv-apisandbox.nic.in/version1.04/authentication.html — fetched 2026-10-09 — official API doc
- [345] https://einv-apisandbox.nic.in/version1.03/generate-irn.html — fetched 2026-10-09 — official API doc
- [346] https://einv-apisandbox.nic.in/version1.03/cancel-irn.html — fetched 2026-10-09 — official API doc; 24 h, reasons
- [347] https://einv-apisandbox.nic.in/version1.03/get-eInvoicedetails.html (+ Get_IRNdetailsbyDocDetails.html) — fetched 2026-10-09 — official; 3-day retrieval
- [348] https://einv-apisandbox.nic.in/onboarding.html — fetched 2026-10-09 — official; IPs, TLS, test report (partly dated)
- [349] https://einvoice1.gst.gov.in/Others/GSPSLIST (data: /documents/gspsjson.json) — fetched 2026-10-09 — official GSP/ERP list (42)
- [351] https://gstzen.in/e-invoicing-api-integration-pricing — fetched 2026-10-09 — vendor (GSP) published pricing
- [352] https://help.open.money/support/solutions/articles/69000860487-is-e-invoicing-applicable-to-nil-rated-or-wholly-exempt-supplies- — fetched 2026-10-09 — vendor FAQ; no official citation

### E-way bill
- [355] https://gstcouncil.gov.in/sites/default/files/2024-05/notification-12-2018-central_tax-english.pdf — fetched 2026-10-09 — official; rule 138 incl. (14) and Annexure, courier provisos
- [357] https://www.gstcouncil.gov.in/hi/node/3130 (+ /sites/default/files/AAR/kar_aar_45_2019_tbppcl_17.09.19.pdf, OCR) — fetched 2026-10-09 — official AAR listing; entry 119 = 4901
- [361] https://docs.ewaybillgst.gov.in/apidocs/pre-requisites.html — fetched 2026-10-09 — official; ~10k txns/month/GSTIN

### GSTR-1
- [365] https://raw.githubusercontent.com/resilient-tech/india-compliance/develop/india_compliance/gst_returns/fields/gstr1.py — fetched 2026-10-09 — open-source code; GSTR-1 JSON keys
- [366] https://raw.githubusercontent.com/resilient-tech/india-compliance/develop/india_compliance/gst_india/utils/gstr_1/sections/nil_rated.py — fetched 2026-10-09 — open-source code; Table 8 shape
- [367] https://raw.githubusercontent.com/resilient-tech/india-compliance/develop/india_compliance/gst_india/utils/gstr_1/__init__.py — fetched 2026-10-09 — open-source; HSN split from 2025-05-01, B2C limit
- [369] https://www.mahagst.gov.in/public/uploads/gstnadvisory/1760596735_345 Reporting of HSN codes in Table 12 and list of documents in table 13 of GSTR 1 1A.pdf — fetched 2026-10-09 — GSTN advisory (1 May 2025) via a state tax site
- [371] https://www.gstcouncil.gov.in/sites/default/files/2024-05/notfctn-78-central-tax-english-2020.pdf — fetched 2026-10-09 — official notification text

### DPDP Rules and DigiLocker
- [380] https://egazette.gov.in/WriteReadData/2025/267650.pdf — fetched 2026-10-09 — official Gazette, DPDP Rules G.S.R. 846(E)
- [381] https://www.mirvolegal.com/insights/dpdp-rules-2025-compliance-timeline/ — fetched 2026-10-09 — law-firm blog (status as at Sep 2026)
- [383] https://cf-media.api-setu.in/resources/Requester-APISpecification-V1_12.pdf — fetched 2026-10-09 — official NeGD API spec
- [384] https://cdn.apisetu.gov.in/portal/assets/Requester-MeriPehchaan-APISpecificationv2.4.pdf — fetched 2026-10-09 — official NeGD spec v2.4 (Sep 2026)
- [385] https://cf-media.api-setu.in/resources/Partners-SOP.pdf — fetched 2026-10-09 — official NeGD SOP (5 Jun 2024)
- [386] https://cf-media.api-setu.in/resources/DigiLocker-Terms-of-User-Requester-june-2025.pdf — fetched 2026-10-09 — official Terms of Use (2 Jun 2025)
- [387] https://www.digilocker.gov.in/assets/FAQ%20DL%20EL_onboarding.pdf — fetched 2026-10-09 — official onboarding FAQ
- [388] https://apisetu.gov.in/digilocker — fetched 2026-10-09 — official resource centre
- [389] https://www.medianama.com/2026/04/223-andhra-pradesh-explores-digilocker-age-tokens-social-media-curbs-children-aged-13-16/ — fetched 2026-10-09 — news

### PIN directory
- [392] https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month — fetched 2026-10-09 — official page (JS app; GODL footer only)
- [393] https://github.com/addypy/datagovindia — fetched 2026-10-09 — open-source README with the resource metadata snapshot
- [394] https://github.com/devzoy/indian-pincode (pipeline/config.py) and https://github.com/code-kasha/bharat-post-dir (postal/importer.py) — fetched 2026-10-09 — open-source code calling the API
- [395] https://einvoice1.gst.gov.in/Others/MasterCodes — fetched 2026-10-09 — official NIC pincode-state mapping pattern

## Operations tooling and integration UI patterns (400 to 499)

### Sentry and GlitchTip
- [400] https://sentry.io/pricing/ — fetched 2026-10-09 — official pricing page; month-to-month prices from its schema.org JSON-LD
- [401] https://docs.sentry.io/organization/data-storage-location/ — fetched 2026-10-09 — official docs
- [408] https://docs.sentry.io/platforms/python/crons/ — fetched 2026-10-09 — official docs
- [409] https://docs.sentry.io/platforms/python/integrations/celery/crons/ — fetched 2026-10-09 — official docs
- [410] https://docs.sentry.io/product/uptime-monitoring/ — fetched 2026-10-09 — official docs
- [411] https://develop.sentry.dev/self-hosted/ — fetched 2026-10-09 — official developer docs
- [413] https://glitchtip.com/pricing — fetched 2026-10-09 — official pricing
- [414] https://glitchtip.com/documentation/install — fetched 2026-10-09 — official docs
- [415] https://glitchtip.com/documentation/uptime-monitoring — fetched 2026-10-09 — official docs
- [416] https://glitchtip.com/sdkdocs/python-django — fetched 2026-10-09 — official docs

### Health checks and uptime
- [418] https://codingjoe.dev/django-health-check/ — fetched 2026-10-09 — official docs (read from the repo's docs/*.md: install, usage, checks, cookbook)
- [419] https://pypi.org/project/django-health-check/ — fetched 2026-10-09 — official package metadata (4.8.0)
- [420] https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/ — fetched 2026-10-09 — official docs
- [421] https://github.com/louislam/uptime-kuma — fetched 2026-10-09 — official README + releases API (2.5.5)
- [422] https://betterstack.com/pricing — fetched 2026-10-09 — official pricing (page text)
- [423] https://uptimerobot.com/pricing/ — fetched 2026-10-09 — official pricing incl. its machine-readable /pricing.md
- [424] https://uptimerobot.com/terms/ — fetched 2026-10-09 — official terms

### Cloudflare R2 and django-storages
- [425] https://developers.cloudflare.com/r2/pricing/ — fetched 2026-10-09 — official docs (updated 1 Oct 2026)
- [426] https://developers.cloudflare.com/r2/api/s3/api/ — fetched 2026-10-09 — official docs
- [427] https://developers.cloudflare.com/r2/api/s3/presigned-urls/ — fetched 2026-10-09 — official docs
- [429] https://developers.cloudflare.com/r2/buckets/object-lifecycles/ — fetched 2026-10-09 — official docs
- [430] https://developers.cloudflare.com/r2/buckets/event-notifications/ — fetched 2026-10-09 — official docs
- [432] https://developers.cloudflare.com/r2/reference/data-location/ — fetched 2026-10-09 — official docs
- [433] https://developers.cloudflare.com/r2/api/tokens/ — fetched 2026-10-09 — official docs
- [434] https://developers.cloudflare.com/fundamentals/api/how-to/roll-token/ — fetched 2026-10-09 — official docs
- [435] https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/ — fetched 2026-10-09 — official docs
- [438] https://developers.cloudflare.com/r2/platform/metrics-analytics/ — fetched 2026-10-09 — official docs

### DPDP Act and analytics
- [442] https://egazette.gov.in/WriteReadData/2023/248045.pdf — fetched 2026-10-09 — official Gazette: DPDP Act 2023 (s.2(f), s.9, Schedule)
- [444] https://www.mondaq.com/india/data-protection/1773554/meity-plans-to-cut-short-dpdp-compliance-timeline-and-notify-cross-border-restrictions-for-sdfs — fetched 2026-10-09 — secondary (law-firm article) on the Jan 2026 proposal
- [446] https://docs.umami.is/docs/faq — fetched 2026-10-09 — official docs
- [447] https://docs.umami.is/docs/install — fetched 2026-10-09 — official docs
- [448] https://docs.umami.is/docs/environment-variables — fetched 2026-10-09 — official docs
- [449] https://github.com/umami-software/umami — fetched 2026-10-09 — official source (src/app/api/send/route.ts, src/lib/crypto.ts, src/tracker/index.ts, prisma/schema.prisma; MIT; v3.4.0)
- [450] https://plausible.io/data-policy — fetched 2026-10-09 — official data policy
- [451] https://plausible.io/self-hosted-web-analytics — fetched 2026-10-09 — official CE vs Cloud comparison
- [452] https://github.com/plausible/community-edition — fetched 2026-10-09 — official repo README + compose.yml (v3.2.1)
- [453] https://matomo.org/faq/general/configure-privacy-settings-in-matomo/ — fetched 2026-10-09 — official FAQ
- [454] https://matomo.org/faq/general/faq_157/ — fetched 2026-10-09 — official FAQ (disableCookies)
- [455] https://matomo.org/faq/general/faq_21418/ — fetched 2026-10-09 — official FAQ (cookieless config_id)
- [456] https://matomo.org/faq/on-premise/matomo-requirements/ — fetched 2026-10-09 — official requirements (+ GitHub releases API: 5.14.1)
- [458] https://posthog.com/docs/self-host — fetched 2026-10-09 — official docs
- [459] https://posthog.com/docs/libraries/js/persistence — fetched 2026-10-09 — official docs
- [460] https://posthog.com/docs/privacy/data-collection — fetched 2026-10-09 — official docs
- [461] https://posthog.com/tutorials/cookieless-tracking — fetched 2026-10-09 — official tutorial
- [462] https://posthog.com/docs/libraries/js/config — fetched 2026-10-09 — official docs

### Stripe
- [463] https://docs.stripe.com/webhooks — fetched 2026-10-09 — official docs
- [464] https://docs.stripe.com/events/manage-webhook-endpoints — fetched 2026-10-09 — official docs
- [465] https://docs.stripe.com/event-destinations — fetched 2026-10-09 — official docs
- [466] https://support.stripe.com/questions/why-is-stripe-trying-to-reach-my-webhook-endpoints — fetched 2026-10-09 — official support article
- [467] https://docs.stripe.com/keys — fetched 2026-10-09 — official docs
- [468] https://docs.stripe.com/keys/restricted-api-keys — fetched 2026-10-09 — official docs
- [469] https://docs.stripe.com/sandboxes — fetched 2026-10-09 — official docs (+ /testing-use-cases and /sandboxes/dashboard/manage)
- [470] https://docs.stripe.com/workbench/overview — fetched 2026-10-09 — official docs
- [471] https://docs.stripe.com/workbench/health — fetched 2026-10-09 — official docs
- [472] https://docs.stripe.com/development/dashboard/request-logs — fetched 2026-10-09 — official docs (legacy Developers Dashboard)
- [473] https://docs.stripe.com/connect/handling-api-verification — fetched 2026-10-09 — official docs
- [474] https://docs.stripe.com/connect/dashboard/review-actionable-accounts — fetched 2026-10-09 — official docs
- [475] https://docs.stripe.com/api/idempotent_requests — fetched 2026-10-09 — official API reference

### Shopify
- [476] https://shopify.dev/docs/apps/build/webhooks — fetched 2026-10-09 — official docs
- [477] https://shopify.dev/docs/apps/build/webhooks/troubleshoot — fetched 2026-10-09 — official docs
- [478] https://shopify.dev/docs/apps/build/webhooks/verify-deliveries — fetched 2026-10-09 — official docs
- [479] https://shopify.dev/docs/apps/build/authentication-authorization/manage-credentials — fetched 2026-10-09 — official docs
- [480] https://shopify.dev/docs/api/usage/access-scopes — fetched 2026-10-09 — official docs
- [481] https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes — fetched 2026-10-09 — official docs
- [482] https://shopify.dev/docs/apps/build/authentication-authorization/cli-app-authentication — fetched 2026-10-09 — official docs

### Zapier
- [483] https://help.zapier.com/hc/en-us/articles/8496290788109-Manage-your-app-connections — fetched 2026-10-09 — official help centre
- [484] https://help.zapier.com/hc/en-us/articles/8496241726989-Replay-Zap-runs — fetched 2026-10-09 — official help centre
- [485] https://help.zapier.com/hc/en-us/articles/19220226086797-What-is-replay — fetched 2026-10-09 — official help centre
- [486] https://help.zapier.com/hc/en-us/articles/8496291148685-View-and-manage-your-Zap-history — fetched 2026-10-09 — official help centre
- [487] https://help.zapier.com/hc/en-us/articles/8496289225229-Manage-notifications-when-errors-occur-in-Zap-workflows — fetched 2026-10-09 — official help centre
- [488] https://help.zapier.com/hc/en-us/articles/8496216132621-Zap-is-not-running — fetched 2026-10-09 — official help centre

### Svix and Hookdeck
- [489] https://docs.svix.com/retries — fetched 2026-10-09 — official docs (updated 18 Sep 2026)
- [490] https://docs.svix.com/receiving/verifying-payloads/how-manual — fetched 2026-10-09 — official docs
- [491] https://docs.svix.com/idempotency — fetched 2026-10-09 — official docs
- [492] https://docs.svix.com/receiving/using-app-portal/replaying-messages — fetched 2026-10-09 — official docs
- [493] https://api.svix.com/api/v1/openapi.json — fetched 2026-10-09 — official OpenAPI spec (rotate grace, recover, replay-missing, stats, operational events)
- [494] https://github.com/standard-webhooks/standard-webhooks — fetched 2026-10-09 — official spec + Python library (5-minute tolerance)
- [495] https://hookdeck.com/docs/retries — fetched 2026-10-09 — official docs
- [496] https://hookdeck.com/docs/deduplication — fetched 2026-10-09 — official docs
- [497] https://hookdeck.com/docs/issues — fetched 2026-10-09 — official docs (+ /docs/issue-triggers)
- [498] https://hookdeck.com/docs/limits — fetched 2026-10-09 — official docs
- [499] https://hookdeck.com/docs/events — fetched 2026-10-09 — official docs (+ /docs/guides/how-to-pause-connections, /docs/bookmarks)
