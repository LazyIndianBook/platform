# Couriers and other integrations for the ExamLeaf admin panel: research

Date: 9 October 2026. For the Admin Control Panel plan (Shipping; Settings → Integrations; System → Webhooks).
Scope: courier aggregators and logistics APIs (sections 1 to 3), the other third-party integrations the panel
manages (section 4), and how integration pages are built elsewhere (section 5). Sources are numbered [n] and listed
with URLs in `sources-integrations.md`, in four ranges: 1 to 99 couriers and design patterns, 200 to 299 payments
and messaging, 300 to 399 accounting, tax and government, 400 to 499 operations tooling and UI patterns.
"Review site", "forum", "blog" or "news" marks a fact that does not come from the vendor or the government.
Prices are as published on the date fetched; GST is stated where the source states it.

## 0. What matters for the plan

1. **Shiprocket has no sandbox.** "Any requests made using the valid API credentials will affect the real-time data
   in your Shiprocket account" [1]. Testing is a recorded-fixture fake in CI plus a live smoke order cancelled before
   pickup (cancellation reverses the freight to the wallet [11]).
2. **Auth is a password grant.** A dedicated API user's email and password give a JWT valid for 10 days [1][2];
   the API user can be limited to chosen modules and denied buyer details [1]. Store the password encrypted; cache one
   token; renew it before day 10 or on a 401.
3. **Tracking webhooks are weak.** One URL per account, an optional static token sent as `x-api-key`, no signature,
   no event id, the endpoint must answer 200, and the URL must not contain "shiprocket", "kartrocket", "sr" or "kr"
   [1]. So: check the token in constant time, store the raw body, dedupe by hash, and re-read tracking by AWB before
   any change that moves money or stock. A polling sweep catches missed events.
4. **Two status-code tables.** Shiprocket numbers order statuses and shipment statuses differently (In Transit is 20
   in one, 18 in the other) and the webhook carries one of each [1]. Map on `shipment_status_id`.
5. **Money data exists per order, not as a remittance feed.** COD is remitted D+8 working days after delivery, paid on
   Mondays, Wednesdays and Fridays, so about 10 working days [5]; Early COD costs 0.99 % (D+2), 0.69 % (D+3) or
   0.49 % (D+4) of the COD amount [6]. `orders/show` returns `remittance_date`, `remittance_utr` and
   `remittance_status`; the wallet statement API returns every debit and credit with its AWB; the discrepancy API
   returns weight disputes, which must be contested within 7 working days or are auto-accepted [1][8].
6. **Plans (October 2026):** Lite free, Business ₹199 a month, Advanced ₹499, Pro ₹799; Shiprocket's own "average
   shipment cost" ₹45, ₹41, ₹39 and ₹36 [3]. A plan fee is refunded at 100, 500 or 1,000 shipments in a month [3].
7. **India Post fits books better than any courier, but without COD.** Gyan Post (since 1 May 2025) carries
   qualifying books tracked, by surface, for ₹20 up to 300 g, ₹25 up to 500 g and ₹35 up to 1 kg, before taxes
   [60][62][63]. It covers books "prescribed in syllabus ... by recognized boards" and textbooks for competitive
   examinations [62][63]: whether ExamLeaf's sample-paper books qualify must be confirmed in writing by the postal
   division before the panel offers it. Book Post is ₹4 for the first 50 g and ₹3 for each further 50 g, sent open
   and untracked [60][61]. India Post COD needs a bulk-customer contract [70].
8. **Assam is a remote zone.** For Shiprocket, any shipment with either end in the North East is Zone E [15]; for
   Delhivery the North East (except Manipur, which is Zone F) is Zone E [48]. One aggregator's 2 October 2026 chart
   puts 500 g by surface at ₹54 to ₹70 to the "special region" against ₹31 to ₹45 within a city, and 1 kg at ₹88 to
   ₹113 against ₹47 to ₹62, GST included [86].
9. **Delhivery direct** offers the staging environment Shiprocket lacks, with separate test and live tokens [32], but
   its tracking push is set up by Delhivery's team (5 to 6 working days) [35], pulls are limited to 750 requests per
   5 minutes per IP [34], and generating a new token kills the old one at once [45]. COD is remitted within 48 hours
   if the wallet is positive [47].
10. **Build one carrier interface with two implementations now:** "manual" (today's counter flow: staff type the
    courier and number, which already covers India Post) and Shiprocket. Add Delhivery or the India Post bulk API only
    when volume pays for it.
11. **Other integrations** (section 4) and the connections page (section 5) follow the same rules: secrets encrypted
    and rotatable, every inbound event stored raw and deduplicated, every outbound call logged and retried with
    backoff, a dead-letter list with replay, and a test mode per integration.

## 1. Shiprocket API v1 (apiv2.shiprocket.in)

### 1.1 How the account works
- **Wallet.** Freight and COD charges are debited from a prepaid wallet when a shipment is processed, reversed on
  cancellation or courier reassignment; RTO freight and excess-weight charges are debited later; COD charges are
  reversed when a shipment goes RTO [11].
- **Plans** [3]:

  | Plan | Fee | "Avg shipment cost" | Positioned for | Fee refunded at |
  |---|---|---|---|---|
  | Lite | free | ₹45 | up to 5 orders a month | - |
  | Business | ₹199 a month | ₹41 | 5 to 50 | 100 shipments in a month |
  | Advanced | ₹499 a month | ₹39 | 50 to 200 | 500 |
  | Pro | ₹799 a month | ₹36 | 3,000 to 10,000 | 1,000 |

  All plans include label and manifest generation, tracking, the rate calculator, several pickup locations, COD
  reconciliation, bulk processing and email and SMS notifications [3]. (A 2023 help article still lists the older
  Lite/Basic ₹1,000/Advanced ₹2,000/Pro ₹3,000 plans with rates from ₹26.27 to ₹20.34 per 0.5 kg before GST [4];
  the pricing page supersedes it.)
- **Couriers** are identified by `courier_company_id`, for example 10 Delhivery, 43 Delhivery Surface, 33 Xpressbees,
  51 Xpressbees Surface, 48 Ekart Logistics, 1 Blue Dart, 55 Blue Dart Surface, 6 DTDC Surface, 14 Ecom Express
  Surface, 29 Amazon Shipping 1 kg [1].
- **Zones:** A within a city, B within a state or region, C metro to metro, D rest of India excluding the North East
  and J&K, E "if one or both cities are in North East states, J&K, Kerala and Himachal Pradesh" [15].

### 1.2 Authentication
- `POST https://apiv2.shiprocket.in/v1/external/auth/login` with `{"email", "password"}` of an **API user** returns a
  JWT; "The validity of this token is 10 days"; send `Authorization: Bearer <token>`; `POST /v1/external/auth/logout`
  ends it [1][2].
- API users are created under Settings → API → Add New API User, with an email different from the main login, a
  choice of **Modules to Access**, and **Buyer's Details Access: Allowed / Not Allowed**; the password is shown once
  [1]. The screen is "Add New API User", which suggests several can exist, so a rotation can create the new user,
  switch, then delete the old one (not verified).
- Design: one cached token per account (encrypted, with its expiry), renewed by a single worker under a lock at day 9
  or after a 401; never one login per request.

### 1.3 Identifiers
- The `order_id` we send is our reference (max 50 characters); the `order_id` Shiprocket returns is its own, and "All
  our APIs will use this Shiprocket order id ... unless stated otherwise" [1]. A `shipment_id` comes back with the
  order; the AWB (`awb_code`) after courier assignment [1].
- An `order_id` "cannot be equal to an already existing id", cancelled ones included; a 422 "despite filling in the
  correct details" usually means a reused id [1]. Use the order number for the first parcel and a suffix for a
  re-shipment (`EL-2026-000123-R1`).

### 1.4 Endpoints a panel needs
All under `https://apiv2.shiprocket.in/v1/external` unless noted [1].

| Step | Call | Notes |
|---|---|---|
| Pickup addresses | `GET /settings/company/pickup`, `POST /settings/company/addpickup` | `pickup_location` is a nickname, max 36 characters; orders must name an existing one |
| Create order | `POST /orders/create/adhoc` (custom channel), `POST /orders/create` (named channel, needs inventory sync) | returns `order_id`, `shipment_id`, `status: NEW` |
| Change order | `POST /orders/update/adhoc` (items only, before Ready to Ship), `POST /orders/address/update`, `PATCH /orders/address/pickup` | |
| Rates and couriers | `GET /courier/serviceability/` | see 1.6 |
| Assign courier | `POST /courier/assign/awb` `{shipment_id, courier_id?, status?: "reassign"}` | reassign "only once in 24 hours" |
| Pickup | `POST /courier/generate/pickup` `{shipment_id: [one id], pickup_date?: ["YYYY-MM-DD"], status?: "retry"}` | AWB first; a Sunday or holiday moves to the next date |
| Manifest | `POST /manifests/generate` `{shipment_id: [...]}`, `POST /manifests/print` `{order_ids: [...]}` | needs AWB and pickup |
| Label, invoice | `POST /courier/generate/label` `{shipment_id: [...]}`, `POST /orders/print/invoice` `{ids: [...]}`, `POST /courier/generate/label-invoice` `{shipment_ids: [max 200]}` | PDF URLs; the combined call reports `success_count`, `error_count`, `error_file_url` and "completed: true ... does not guarantee every shipment succeeded" |
| All in one | `POST /shipments/create/forward-shipment` | order, AWB, pickup, label and manifest in one call; its "Invalid Data" example answers HTTP 200 |
| Track | `GET /courier/track/awb/{awb}`, `POST /courier/track/awbs` (max 50), `GET /courier/track/shipment/{id}`, `GET /courier/track?order_id=&channel_id=` | |
| NDR | `GET /ndr/all`, `GET /ndr/{awb}`, `POST /ndr/{awb}/action` | see 1.9 |
| Cancel | `POST /orders/cancel` `{ids}`, `POST /orders/cancel/shipment/awbs` `{awbs: [max 2000]}` | shipments only before "Out for Pickup" |
| Returns | `POST /orders/create/return`, `POST /orders/create/exchange`, `POST /orders/edit`, `GET /orders/processing/return` | serviceability with `is_return=1` |
| Order detail | `GET /orders/show/{id}`, `GET /orders`, `POST /orders/export` | detail includes the COD remittance fields |
| Money | `GET /account/details/wallet-balance`, `GET /account/details/statement`, `GET /billing/discrepancy` | see 1.10 |
| PIN codes | `GET /open/postcode/details`; `serviceability.shiprocket.in/v1/external/blocked-pincodes/upload` and `/block-pincodes/get` | block PINs that keep failing |

### 1.5 Creating an order
- Required: `order_id`, `order_date`, `pickup_location`, `billing_customer_name`, `billing_address`, `billing_city`
  (max 30 characters), `billing_pincode`, `billing_state`, `billing_country`, `billing_email`, `billing_phone`,
  `shipping_is_billing` (and the `shipping_*` fields when false), `order_items[]` (`name`, `sku`, `units`,
  `selling_price`, optional `discount`, `tax`, `hsn`), `payment_method` (COD or Prepaid), `sub_total`, `length`,
  `breadth`, `height` (cm) and `weight` (kg). Optional: `channel_id`, `comment` or `reseller_name` ("Reseller: name"
  prints a From line), `shipping_charges`, `total_discount`, `invoice_number`, `ewaybill_no`, `customer_gstin` [1].
- "Be sure to input the correct calculated sub_total amount. The total is not calculated automatically through the
  API" [1]. For COD this is the cash the courier collects: the panel must compute it from the order and refuse to
  send a mismatch.
- `billing_email` is required [1]: ExamLeaf sends the buyer's address (the processor sees it) or a per-order alias;
  a choice for the privacy notice.

### 1.6 Serviceability, rates and the recommendation
- `GET /courier/serviceability/?pickup_postcode=&delivery_postcode=` plus either `order_id` or `cod` (1/0) and
  `weight` (kg); optional `length`, `breadth`, `height`, `declared_value`, `mode` (Surface/Air), `is_return`,
  `qc_check`, `couriers_type`, `only_local` [1].
- Each of `data.available_courier_companies[]` carries `courier_company_id`, `courier_name`, `rate`,
  `freight_charge`, `cod_charges`, `rto_charges`, `coverage_charges`, `other_charges`, `etd`,
  `estimated_delivery_days`, `rating`, `delivery_performance`, `pickup_performance`, `rto_performance`,
  `tracking_performance`, `cod` (0/1), `is_surface`, `min_weight`, `charge_weight`, `zone` (for example `z_e`),
  `cutoff_time`, `pickup_availability`, `call_before_delivery`, `pod_available`, `odablock` and `blocked`; `data`
  also names `recommended_courier_company_id` and `shiprocket_recommended_courier_id` [1].

### 1.7 Tracking: pull and push
- Pull: `tracking_data.shipment_status` plus `shipment_track[]` (current status, delivered date, POD) and
  `shipment_track_activities[]` (`date`, courier `status`, `activity`, `location`, `sr-status`, `sr-status-label`) [1].
- **Webhook** [1]: Settings → API → Webhooks, URL, enable, optional security token. POST, `application/json`; the
  token arrives as `x-api-key`; "Please do not use keywords like shiprocket, kartrocket, sr, or kr in your webhook
  URL"; "The URL should be set to send only code 200 in response". Body: `awb`, `courier_name`, `current_status`,
  `current_status_id`, `shipment_status`, `shipment_status_id`, `current_timestamp` (as `23 05 2023 11:43:52`),
  `order_id` (the channel order id), `sr_order_id`, `awb_assigned_date`, `pickup_scheduled_date`, `etd`, `scans[]`
  (`date` as `2023-05-19 11:59:16`, courier code such as `X-PPOM`, `activity`, `location`, `sr-status`,
  `sr-status-label`), `is_return`, `channel_id`, `pod_status`, `pod`, `qc_image`, `qc_failure_reason`. No signature,
  event id or retry schedule is documented.
- **Shipment status codes** (tracking table) [1]: 1 AWB Assigned, 2 Label Generated, 3 Pickup Scheduled/Generated,
  4 Pickup Queued, 5 Manifest Generated, 6 Shipped, 7 Delivered, 8 Cancelled, 9 RTO Initiated, 10 RTO Delivered,
  11 Pending, 12 Lost, 13 Pickup Error, 14 RTO Acknowledged, 15 Pickup Rescheduled, 16 Cancellation Requested,
  17 Out For Delivery, 18 In Transit, 19 Out For Pickup, 20 Pickup Exception, 21 Undelivered, 22 Delayed,
  23 Partial Delivered, 24 Destroyed, 25 Damaged, 26 Fulfilled, 27 Pickup Booked, 38 Reached at Destination Hub,
  39 Misrouted, 40 RTO NDR, 41 RTO OFD, 42 Picked Up, 43 Self Fulfilled, 44 Disposed Off, 45 Cancelled before
  Dispatched, 46 RTO In Transit, 47 QC Failed, 48 Reached Warehouse, 51 Handover to Courier, 52 Shipment Booked,
  75 RTO Lock, 76 Untraceable, 77 Issue Related to the Recipient, 78 Reached Back at Seller City (plus warehouse,
  international and hyperlocal codes). The order table differs (15 RTO Initiated, 19 Out for Delivery, 20 In Transit,
  36 Undelivered, 51 Picked Up ...) [1]; the sample webhook's IN TRANSIT carries `current_status_id: 20` and
  `shipment_status_id: 18`, one from each table (inferred from the sample).
- What the statuses mean [10]: Pickup Exception triggers an IVR call to the seller; after a first failed delivery the
  courier makes up to three more attempts, then RTO ("different couriers have different reattempt policy"); RTO
  Acknowledged is the seller confirming receipt; an unclaimed RTO becomes Destroyed; lost or damaged shipments carry
  an insurance claim of ₹5,000 or the order value, whichever is lower.

### 1.8 NDR (failed delivery) actions
`POST /ndr/{awb}/action` with `action` = `re-attempt`, `return` or `fake-attempt`, a required `comments`, and
optionally a new `phone`, `address1`, `address2` and `deferred_date`; a fake-attempt claim adds `proof_audio`,
`proof_image` and `remarks`; answer 202 [1]. `GET /ndr/all` (filters `from`, `to`, `search`) lists each NDR with
`reason` (e.g. "Customer Asked For Future Delivery"), `attempts`, `ndr_raised_at`, `escalation_status` and history [1].

### 1.9 Cancellations and returns
- Cancel orders by Shiprocket id (204); cancel shipments by AWB "before the Out for Pickup state", up to 2,000 at a
  time [1]. After pickup nothing cancels: deliver, or ask for RTO through an NDR `return`.
- Returns: a return order names the customer as `pickup_*` and us as `shipping_*`; exchanges link an
  `exchange_order_id` to a `return_order_id` and our pickup and shipping location ids; QC-enabled return couriers
  are filtered with `qc_check=1` [1].

### 1.10 Money: charges, COD, weight
- **Statement:** `GET /account/details/statement?from=&to=&page=` returns rows with `order_id`, `channel_order_id`,
  `awb_code`, `applied_weight`, `charged_weight`, `billed_weight`, `charge`, `description`, `debit_amount`,
  `credit_amount`, `balance_amount`, `created_at` [1]. Passbook entries are Freight Charge, Freight Charge Reversed,
  Excess Weight Charge, RTO Freight Charge, RTO Freight Reversed, COD Charge, COD Charge Reversed, RTO Excess Weight
  Charge and RTO Excess Freight Reversed [11].
- **COD charge:** "a fixed COD charge or COD% of the order value whichever is higher", per courier (their example:
  ₹36 or 2.50 %) [12].
- **COD remittance:** D+8 working days, credited three times a week (Monday, Wednesday, Friday), so "within 10 working
  days after the shipment is delivered" [5]. Early COD: D+2 at 0.99 %, D+3 at 0.69 %, D+4 at 0.49 % of the COD
  amount, GST included (official blog) [6]. Instant COD: up to 70 % the day after shipping for a fee of up to 5 %,
  "exclusively available for a limited set of sellers" [7]. Per order, `GET /orders/show/{id}` returns
  `remittance_date`, `remittance_utr`, `remittance_status` [1]. No remittance-batch API appears in the public
  collection, so batch totals come from the panel's CSV export (Billing → COD Remittance) if needed.
- **Weight discrepancy:** `GET /billing/discrepancy` lists them [1]. Rules [8]: raise a dispute within 7 working days
  or the courier's weight is auto-accepted; product category and subcategory are mandatory, with photos of all three
  dimensions; one dispute per order and the result is final; the disputed amount is held, not deducted, until
  resolved; resolution "7 days or lesser" (another article: "a minimum of 7 days" [9]).

### 1.11 Limits, test mode, support
- HTTP 429 means "You have exceeded the API call rate limit"; no number is published [1]. Batch caps: 50 AWBs per
  tracking call, 2,000 per cancellation, 200 per combined label and invoice [1].
- Errors: 400, 401, 404, 405, 422, 429, 5xx, and "Some APIs may respond with an error message if data is invalid"
  with 200 or 202 [1]. Always read the body.
- No sandbox (point 1 of section 0); the developers page mentions "working in Sandbox" without details [19].
  Integration support: integration@shiprocket.com [1].

### 1.12 Shiprocket's add-ons and whether ExamLeaf needs them
- **Engage 360** (WhatsApp first, IVR fallback): order confirmation, address verification, COD-to-prepaid offers,
  branded tracking updates, broadcasts [14]. Priced as a monthly platform fee plus a per-order price per module shown
  in the panel; the WhatsApp number given to it "can't be used for any other type of WhatsApp product" and the
  service runs through Kaleyra [13]. Skip: it messages buyers (often parents of minors) from a number and a consent
  record outside ExamLeaf's; the same messages are cheap to send as our own utility templates (section 4.2).
- **Fastrr Checkout** (address prefill, one-click checkout, COD controls) [16], once Pickrr's checkout; Shiprocket
  bought Pickrr in a reported US$200 million deal in 2022 [17][18]. It replaces the checkout. Not needed: ExamLeaf
  owns its checkout and Razorpay.
- **Sense:** paid RTO-score and address-verification APIs [1]. Later, if COD refusals hurt; a first-time-COD rule
  costs nothing.
- **Shiprocket's MCP server** logs in with the seller's own email and password from an environment variable [1]: not
  for production use.

### 1.13 Gotchas
From the documentation [1]: reused `order_id` (422); `sub_total` not computed; `pickup_location` must already exist;
reassign once per 24 hours; one shipment per pickup call; errors with HTTP 200; two code tables; two timestamp
formats, both IST without an offset; the forbidden words in the webhook URL; the static webhook token is optional,
so an endpoint without one accepts anyone's POST. From a review site [21] (anecdotal, July and August 2026; 1.2 out
of 5 over 2,163 reviews): deliveries marked "customer unavailable" or "refused" without a real attempt, then RTO;
volumetric-weight charges with rejected disputes; slow support. The defences are in section 3: photographs of each
parcel on the scale, flyers rather than boxes, the NDR call within hours, and fake-attempt claims with proof.

## 2. The alternatives, for a small publisher in Assam

### 2.1 Delhivery, direct or through Delhivery One
- **Account.** Delhivery One (launched August 2023) lets small businesses sign up without a minimum order volume and
  with a minimum wallet recharge of ₹500 (trade news) [51]. API documents and a test console sit inside the portal
  (`ucp.delhivery.com/developer-portal`), against a staging environment [46]; the older public reference is
  `delhivery-express-api-doc.readme.io` [30].
- **Auth.** A static token per account and per environment, sent as `Authorization: Token <key>` [31][44]; "Static
  Token for each client, and for each environment (Test and Production) Token will be Different" [31][32]. In
  Delhivery One, "Request Live API Token" replaces the token and "your old token will stop working immediately"; a new
  token is visible for 5 minutes and can be revealed once [45]. Rotation therefore needs a planned switch: paste,
  test, save, in one sitting.
- **Hosts.** `https://staging-express.delhivery.com` for tests, `https://track.delhivery.com` for production [31].
- **Calls** [33]-[44]:

  | Purpose | Call | Notes |
  |---|---|---|
  | Serviceability | `GET /c/api/pin-codes/json/?filter_codes=<pin>` | COD, prepaid and pickup flags per PIN; "NSZ" means not serviceable |
  | Waybills | `GET /waybill/api/bulk/json/?cl=&token=&count=` | at most 10,000 per request and 50,000 per 5 minutes, then the IP is throttled for a minute; or leave the waybill out and get one in the create answer |
  | Create (manifest) | `POST /api/cmu/create.json`, body `format=json&data={...}` | "client" must match the registered name; the pickup location name is exact and case-sensitive; the characters & \ % # ; are refused unless encoded; seller GSTIN and HSN are mandatory; an e-way bill is required above ₹50,000 |
  | Edit, cancel | `POST /api/p/edit`; cancel with `"cancellation": "true"` | cancellable while Manifested, In Transit, Pending, Open or Scheduled; a cancelled forward parcel becomes "Returned" |
  | Track (pull) | `GET /api/v1/packages/json/?waybill=` | "Only 750 requests per 5 minute per IP" |
  | Track (push) | Delhivery posts each scan to our endpoint | we supply the URL and any auth header; set-up by Delhivery takes "a minimum of 5-6 working days"; "consume all the scans ... and not to put a hard check" |
  | Label | `GET /api/p/packing_slip?wbns=` | JSON that we render ourselves (Code 128 barcode) |
  | Pickup | `POST /fm/request/new/` | one open pickup request per warehouse until it is picked up |
  | Cost estimate | `GET /api/kinko/v1/invoice/charges/.json?md=E|S&cgm=<grams>&o_pin=&d_pin=&ss=Delivered|RTO|DTO` | approximate only; 40 requests a minute |
  | Warehouses | `POST /api/backend/clientwarehouse/create/` and `/edit/` | (paths from a third-party SDK [52]) |
  | NDR | `POST /api/p/update` with `act` = `DEFER_DLV` (at most 6 days after the first pending date), `EDIT_DETAILS` (name, phone, address; only while pending) or `RE-ATTEMPT` | asynchronous: answers a UPL id, checked with `GET /api/cmu/get_bulk_upl/?UPL=` |

- **Statuses.** StatusType `UD` (Manifested, Not Picked, In Transit, Pending, Dispatched = out for delivery), `DL`
  (Delivered), `RT` (In Transit, Pending, Dispatched on the way back) and `DL` + `RTO` (returned to us); "Kindly do not
  hardcode the flow" [42]. A pushed scan carries `Status`, `StatusDateTime`, `StatusType`, `StatusLocation`,
  `Instructions`, `NSLCode`, `AWB`, `ReferenceNo` [35]. NDR eligibility is by NSL code (`EOD-74`, `EOD-15` ...) [37].
- **Money.** COD remitted "within 48 hours", only while the wallet is positive [47]; rate card by zone A to F,
  Zone E "Special Zones (Jammu, HP, North East Excl. Manipur)", Zone F including Manipur, plus destination-city
  surcharges in some metros [48]. Chargeable weight is the higher of dead and volumetric weight, but "for shipments
  that are packed in flyers, we charge only basis dead weight upto 1 KG"; weight claims are only for delivered
  shipments [49]. SmartNDR (paid) chases failed deliveries by WhatsApp and AI calls in English or Hindi, up to three
  calls two hours apart [50].
- **Ecom Express** is now Delhivery's: CCI approved the acquisition of at least 99.4 % for up to ₹1,407 crore on 17
  June 2025 (stock-exchange filing) [53].

### 2.2 India Post
- **Book Post** (Post Office Regulations, 2024) [60][61]: ₹4 for the first 50 g and ₹3 for each further 50 g; up to
  5 kg; posted open or in an unfastened cover that can be inspected; an envelope between 140 × 90 mm and 353 × 250 mm;
  marked "Book Post"; untracked (whether registration can still be added since September 2025 is not verified), and
  with no COD. A parcel that breaks the rules is
  charged as a letter or parcel at double the shortfall. 300 g costs ₹19, 500 g ₹31, 1 kg ₹61.
- **Gyan Post** (Regulation 92A, G.S.R. 263(E) of 28 April 2025, from 1 May 2025) [62][63][64]: for books "prescribed
  in syllabus for correspondence and regular courses ... by recognized boards of education, universities" or
  statutory bodies, literature of social, cultural or religious nature, and textbooks for competitive examinations;
  no periodicals, no advertisements beyond book lists, the printer's or publisher's name in each book,
  "non-commercial" content, an invoice for the packet allowed. Tracking is mandatory, transmission by surface,
  300 g to 5 kg. Tariff, excluding taxes: up to 300 g ₹20, 301 to 500 g ₹25, 501 to 1,000 g ₹35, up to 2 kg ₹50, 3 kg
  ₹65, 4 kg ₹80, 5 kg ₹100 [60][63]. An ineligible packet is reclassed as India Post Parcel (Retail) and charged
  double the shortfall on delivery [62].
- **Registered Post** merged into Speed Post on 1 September 2025, under a directive of 2 July 2025 [67]; registration
  (delivery only to the addressee) is now a value-added service of Speed Post at ₹5 plus GST per item [65].
- **Speed Post** (inland document tariff from 1 October 2025, the first change since 2012, as reported by the
  government broadcaster) [65]: up to 50 g ₹19 local and ₹47 elsewhere; 51 to 250 g ₹24 local, ₹59 up to 200 km, ₹77
  beyond 2,000 km; 251 to 500 g ₹28 local and ₹70 to ₹93 by distance; GST extra; 10 % off for students, 5 % for new
  bulk customers; OTP delivery, online payment and SMS notifications added. A newspaper gave different per-50 g rates
  for the same change [66]: the counter or the Tariff API below is the authority. July 2026 notifications define
  everything that is not a document (letters, banking items, IDs, greeting cards up to 500 g) as a **parcel**, so
  books go at parcel rates; they also add premium "24 Speed Post" and "48 Speed Post" from 1 August 2026, only in
  Delhi, Mumbai, Chennai, Kolkata, Bengaluru and Hyderabad (news) [68][69]. The Speed Post parcel tariff for 2026 is not verified here; the Tariff API
  below returns it.
- **API, for bulk (contract) customers only** [70]: the request goes through the postal circle's marketing executive
  to a CEPT ticket (HDMS); integration by XML over API or SFTP (`data.cept.gov.in`), from whitelisted public IPs.
  Inbound: a booking manifest (article number, our reference, `ShipmentMethodOfPayment` = `CONTRACT` or `COD` with
  the amount, weight, insured value, proof of delivery) or a pickup API (GraphQL, token valid 60 minutes, refresh
  token). Outbound: booked, delivered, not delivered, returned and last-event files, kept 30 days, with event codes
  such as `ITEM_BOOK`, `ITEM_DISPATCH`, `ITEM_DELIVERY`, `ITEM_NONDELIVER`, `ITEM_RETURN`. A Tariff API
  (`https://api.cept.gov.in/tariff/api/values/gettariff`, JSON, IP-whitelisted) prices Speed Post, Business Parcel
  and registered services by PINs, weight and dimensions. The document is version 6.1 of 2021; the post office's new
  software (APT, "IT 2.0") went national in August 2025 (news) [71], so ask CEPT for the current version.
- **COD at India Post** exists for contracted e-commerce customers (a 2016 government release, as reproduced by a tax
  site [72]; the booking XML of [70] has a COD payment method); remittance takes 7 to 10 days (blog, not verified)
  [87].
- The codebase already notes that India Post's public tracking page needs a CAPTCHA and falls back to 17TRACK
  (`shop/models.py`, `Shipment.TRACKING_URLS`).

### 2.3 Other aggregators and couriers

| Name | What it is | API access | Tracking push | Test environment | Published prices |
|---|---|---|---|---|---|
| NimbusPost | aggregator | API key and secret from Settings → API → API Credentials (integrator guide) [88] | webhooks (integrator pages, not verified) | not found | from ₹25.50 per 500 g (up to 300 orders a month), ₹24 (300 to 1,000), ₹19 (1,000+); NDR automation and early COD as add-ons [80] |
| iThink Logistics | aggregator | `access_token` and `secret_key` in the JSON body, issued by their team [81] | not verified | `pre-alpha.ithinklogistics.com` [81] | through a manager; at most 25 orders per sync call [81] |
| Shipway | tracking and notification platform, also aggregates | "Contact Us For API's" [82] | - | - | not published |
| Pickrr | bought by Shiprocket (2022) [17][18] | - | - | - | - |
| Blue Dart | direct contract | APIs on DHL's developer portal; a JWT from an authenticator API with client id and secret [83] | - | - | contract |
| DTDC | direct contract | Entity id and pin plus developer id and pin from DTDC sales [84] | polling | sandbox and production [84] | contract |
| Xpressbees | direct contract | username and password for a token, plus per-endpoint "XB keys" and a business account name from the manager [85] | polling and webhooks [85] | - | contract |
| Ekart, Amazon Shipping | through aggregators | - | - | - | in [86] |

### 2.4 Serviceability in Assam and the North East
- Zone rules make almost every ExamLeaf parcel outside its own city a remote-zone parcel: Shiprocket's Zone E is
  "one or both cities" in the North East [15]; Delhivery's E is the North East except Manipur, and F includes Manipur
  [48]; the iCarry chart calls it "Special Region" [86].
- Network sizes claimed by a September 2026 blog: Delhivery 16,700 to 18,700+ PINs, Xpressbees 19,000+, DTDC
  15,000+, Blue Dart 17,000+, Ecom Express 27,000+ [87]; Shiprocket advertises 19,000+ PINs [3]; India Post moved its
  1.64 lakh post offices onto its new software in August 2025 (trade news) [71].
- Remote PINs ("ODA", out of delivery area: "remote areas where the majority of courier partners refuses to deliver")
  can be blocked per courier or for the account in Shiprocket [20], through its blocked-PIN API, and are flagged per
  courier (`odablock`) in the serviceability answer [1].
- Before launch: run the serviceability call for every PIN of the North-East districts in the `PinCode` table (it
  already stores districts, from data.gov.in), store the answers, and show the panel a map-free table of PINs with no
  COD courier and PINs with no courier at all; those go by India Post.

### 2.5 What a 300 g to 1 kg parcel costs (₹)

| Service | 300 g | 500 g | 1 kg | Tracked | COD | Source |
|---|---|---|---|---|---|---|
| India Post Book Post | 19 | 31 | 61 | no | no | [60] |
| India Post Gyan Post (if eligible; plus taxes) | 20 | 25 | 35 | yes | no | [60][63] |
| Speed Post, document tariff (books are parcels: [68]) | - | 28 (local), 70 to 93 by distance | not verified | yes | contract | [65] |
| Delhivery Surface via an aggregator, city / special region (GST incl.) | as 500 g | 44.78 / 70.16 | 61.20 / 111.95 | yes | ₹33.92 or 1.63 % | [86] |
| Xpressbees Surface, same | as 500 g | 32.20 / 63.25 | 62.10 / 112.70 | yes | ₹25.96 or 1.36 % | [86] |
| Ekart Surface, same | as 500 g | 34.19 / 54.14 | 47.01 / 94.04 | yes | ₹33.92 or 1.63 % | [86] |
| Amazon Shipping Surface, same | as 500 g | 31.35 / 56.99 | 52.72 / 88.34 | yes | ₹27.14 or 1.36 % | [86] |

Couriers charge a 0.5 kg minimum (`min_weight` 0.5 in Shiprocket's answer) [1], so a 300 g book costs the same as a
500 g one. RTO usually costs the forward freight again [86]; a COD parcel that comes back costs freight twice and
earns nothing.

### 2.6 COD and remittance

| Provider | COD fee | Remittance | Source |
|---|---|---|---|
| Shiprocket | fixed or %, whichever is higher, per courier | D+8 working days, paid Mon/Wed/Fri (about 10 working days); Early COD D+2/D+3/D+4 for 0.99/0.69/0.49 %; Instant COD for some sellers | [5][6][7][12] |
| Delhivery One | cash-handling charge in the rate card | within 48 hours, wallet must be positive | [47][48] |
| NimbusPost | in the rate card | "Early COD payouts" add-on, timeline not published | [80] |
| India Post | under the contract | 7 to 10 days (blog, not verified) | [70][87] |

### 2.7 Recommendation
1. **Shiprocket first** (Lite plan; move to Business at about 50 parcels a month, where the ₹199 fee is refunded at
   100): self-serve, the widest documented API of the aggregators (NDR actions, per-order remittance, weight
   disputes, statement), several couriers behind one integration, so courier choice per PIN is data, not code.
2. **India Post stays**, through today's manual flow: Book Post or Gyan Post for prepaid orders where the price
   difference is large (₹25 against ₹54 to ₹70 for 500 g into the North East), and for PINs no courier serves. Ask
   the Guwahati postal division in writing whether ExamLeaf's sample-paper books qualify for Gyan Post; if they do,
   it becomes the default for prepaid book orders, and the bulk-customer API becomes worth the paperwork.
3. **Delhivery direct later**, if one courier carries most parcels and the rates justify a second integration; its
   staging environment then makes testing easier than Shiprocket's.

## 3. The courier integration the panel needs

What exists: `Shipment` (courier from a fixed list with India Post as the default, `tracking_number`,
`tracking_url`, `shipped_at`, `delivered_at`), the order states pending → paid → packed → shipped → delivered (plus
cancelled and refunded), the `PinCode` table with states and districts, `WebhookEvent` (Razorpay: event id plus body
hash, events older than 7 days refused), Celery tasks retried with `retry_backoff=60`, `retry_backoff_max=3600`
and `max_retries=8` (the refund task), a `/health/` check that pings the workers, and `cryptography` in the requirements.
The design reuses all of it.

### 3.1 Shape
- **One carrier interface, two implementations from day one:** `manual` (today's flow: staff type the courier and the
  number; tracking by the courier's page or 17TRACK) and `shiprocket`. Methods: `quote`, `book` (order plus AWB),
  `label`, `schedule_pickup`, `manifest`, `cancel`, `track(awbs)`, `ndr_action`, `parse_webhook`. A dict maps the
  carrier name to its class; nothing more.
- **Every call runs in a Celery task**, except the rate quote on the booking screen (3-second timeout, answer cached
  10 minutes, the last good answer shown when Shiprocket is down).

### 3.2 Data (the minimum)
- `Shipment` gains `carrier`, `status` (our shipment state, 3.6), `external_order_id`, `external_shipment_id`,
  `courier_company_id`, `label` (our stored copy of the PDF), `weight_g`, `charged_weight_g`, `quoted_rate`,
  `cod_amount`, `last_event_at`, `pickup_location`.
- `ShipmentEvent`: shipment, source, the carrier's code and label, our status, `occurred_at`, location, the raw scan,
  and a unique digest. It is the parcel's timeline and the deduplication key in one.
- `IntegrationAccount`, one row per integration and mode (test or live): encrypted credentials, cached token and its
  expiry, webhook token (current and previous), `rotate_by`, `last_success_at`, `last_error_at`, `last_error`,
  circuit state. The plan's `ApiKey` model is for keys we issue; this one is for keys others issue to us.
- `IntegrationCall` (the log, 3.10) and `IntegrationFailure` (the dead-letter list, 3.10).
- `ShipmentCharge` (freight, COD, RTO freight, excess weight, reversals; unique by the statement line) and
  `CodRemittance` (expected amount and date, remitted amount, UTR, date, state).
- NDR cases and weight disputes are items of the panel's inbox with a deadline and the shipment attached; a typed
  model only if their queries outgrow the inbox.
- `PickupLocation` mirrors the carrier's pickup nicknames; one row until a second store exists.

### 3.3 Credentials
- Encrypt with `cryptography`'s `MultiFernet`: keys from the environment, newest first; it encrypts with the first
  key, decrypts with any, and `rotate()` re-encrypts a token under the first key keeping its timestamp [92]. A
  management command rotates every row after a key change.
- The panel never shows a stored secret: it shows the last four characters, who set it and when, and offers
  "Replace", "Test connection" and "Revoke".
- Shiprocket: the API user's email and password; the token is cached (encrypted) with `expires_at` = issue + 10 days
  [1], renewed at day 9 by one worker under a lock, and once on a 401. Rotation: create a new API user in Shiprocket,
  paste, test, save, delete the old user. A reminder at `rotate_by` (90 days is our policy, not Shiprocket's).
- Webhook token: generated by us (32 random bytes), shown once to paste into Shiprocket; the previous token is still
  accepted for 24 hours after a rotation.
- Delhivery, if added: a new token kills the old one immediately [45], so "Replace token" tests the new token before
  saving, in one sitting.

### 3.4 Choosing the courier for an order
- Inputs: the pickup PIN, the delivery PIN, the parcel weight (the sum of `Product.weight_grams`, which exists but
  defaults to 0 and must be filled, plus the packing), the dimensions (a flyer by default), COD or prepaid, the
  declared value. The HSN code per product (default 4901) goes into the order items [1].
- Ask `serviceability`, drop couriers with `cod: 0` for COD orders and any `blocked` or `odablock` one, then rank by
  our rule: the lowest `rate` among couriers rated 4 or more that deliver within N days; ties go to Shiprocket's
  `recommended_courier_company_id` [1]. Show the top three with rate, ETD, rating, COD and RTO charge; staff may
  override; the chosen quote is stored on the shipment and compared with what is billed (3.9).
- Our own numbers replace Shiprocket's ratings once they exist: per courier and destination district, the share
  delivered, the share returned and the median days, from `ShipmentEvent`.
- For a prepaid order, show India Post's price beside the couriers (Book Post, and Gyan Post if confirmed), from a
  tariff table with effective dates.

### 3.5 The packing room: label, pickup, manifest
1. Scan the order, weigh the parcel, take one photograph of it on the scale with the label side up (the evidence
   for weight disputes and fake-attempt claims), press Book. The task creates the Shiprocket order and assigns the
   AWB; it is idempotent: if the shipment already has external ids it does not create again (Shiprocket would refuse
   the repeated `order_id` anyway [1]).
2. The label PDF is fetched once and stored with us, so a reprint never depends on Shiprocket's link. ExamLeaf prints
   its own GST invoice or bill of supply, so Shiprocket's invoice is not used.
3. Pickup: one call per shipment [1], grouped in the panel by pickup date; the courier's `cutoff_time` is shown.
4. Manifest at handover; each parcel is scanned as handed over; a missing scan is a discrepancy before the van leaves.
5. Cancel from the panel until "Out for Pickup" [1]; after that, only an RTO request.

### 3.6 Tracking: webhook first, polling as the net
- **Endpoint** `/api/hooks/parcel-events/` (no forbidden words [1]). Compare `x-api-key` with the current or previous
  token (`hmac.compare_digest`); store the raw body and its SHA-256 (unique); answer 200 at once; process in a task.
- **Processing.** Each scan in the payload becomes a `ShipmentEvent` keyed by a digest of (AWB, code, date,
  activity), so a scan repeated in later payloads is stored once. The new status comes from the mapping below and is
  applied only if it moves forward (the RTO branch is its own sequence). Before marking delivered, returned or lost,
  the task re-reads `GET /courier/track/awb/{awb}` [1]: the webhook is unsigned.
- **Polling.** Every 2 hours, shipments that are not final and have had no event for 6 hours are re-read in batches of
  50 (`POST /courier/track/awbs`) [1]; final states stop polling; a parcel without movement for 5 days opens an inbox
  item.
- **Parcels sent by hand** (the manual carrier, India Post included) can be tracked by 17TRACK's API: register the
  number, receive pushes; header `17token`, 40 numbers per request, 3 requests a second, a one-time 200 free numbers
  and paid quota after that [93]. Until volume justifies it, the tracking link (today's behaviour) is enough.
- **Our states and the Shiprocket shipment codes** [1] (Delhivery and India Post map the same way from their codes
  [42][70]):

  | Our shipment status | Shiprocket shipment codes | Effect on the order |
  |---|---|---|
  | booked | 1, 2, 3, 4, 5, 15, 19, 27, 52 | stays packed |
  | pickup problem (inbox) | 13, 20 | stays packed |
  | in transit | 6, 18, 22, 38, 39, 42, 48, 51 | shipped, at the first one |
  | out for delivery | 17 | shipped |
  | delivered | 7, 26 | delivered, after the re-read; COD remittance expected |
  | delivery failed (NDR) | 21, 77 | shipped; NDR case opens |
  | returning (RTO) | 9, 40, 41, 46, 75 | shipped; no COD expected |
  | returned | 10, 14, 78 | stock check; COD order cancelled, prepaid order to reship or refund |
  | lost or damaged | 12, 24, 25, 44, 76 | claim; reship or refund |
  | cancelled | 8, 16, 45 | stays packed |
  | partial delivery | 23 | inbox |

  The order states have no "returned"; a returned COD order becomes cancelled with the reason recorded. A decision:
  add a `returned` state, or keep it on the shipment.

### 3.7 Telling the customer
| Event | Email | SMS (DLT template) | WhatsApp (utility template, opted in) |
|---|---|---|---|
| shipped (first "in transit") | yes, with the courier, the AWB and our tracking page | yes | yes |
| out for delivery | - | COD only: "keep ₹X ready" | yes |
| delivered | yes | - | - |
| delivery failed | yes, with a link to choose a date, correct the phone or address, or cancel | yes | yes, with quick replies |
| returning to us | yes | - | - |

Links go to our own domain (the tracking page `/orders/t/<token>/` already exists), which is also what DLT URL
whitelisting needs (section 4.2). No marketing in these messages; SMS and WhatsApp not between 21:00 and 08:00; the
email suppression list applies.

### 3.8 Failed deliveries (NDR)
- A `delivery failed` event opens an inbox item with the reason, the attempt count and a deadline: couriers make up
  to three more attempts before RTO, with policies differing by courier [10]; Delhivery allows a deferred date at most
  6 days after the first failure [37]. Default deadline: 24 hours.
- The customer gets the link (3.7). Their answer queues the API action; staff see it on the item.
- Staff actions: call (the outcome is logged), re-attempt with a date, phone or address (`action: re-attempt`),
  dispute a fake attempt with proof (`fake-attempt`), or return (`return`) [1]. Delhivery's equivalents are
  `RE-ATTEMPT`, `DEFER_DLV` and `EDIT_DETAILS`, asynchronous with a UPL id [37].
- Reported: the NDR rate and the NDR-to-delivered rate per courier and district.

### 3.9 Money: RTO, COD, weight, cost
- **RTO.** "Returning" warns the inbox; "returned" makes the packing room scan the parcel back in, judge it sellable or
  damaged, restock it through the stock movement, and acknowledge it (Shiprocket's RTO Acknowledged is done in its
  panel; no API found). The cost (forward freight, RTO freight, the COD charge reversed) is recorded.
- **COD.** On delivery of a COD parcel: a `CodRemittance` row with the expected amount (the order total) and the
  expected date (delivered + 10 working days [5], or D+2 to D+4 with Early COD less its fee [6]). Daily, awaiting rows
  are checked with `GET /orders/show/{id}` (`remittance_status`, `remittance_utr`, `remittance_date`) [1]; a row past
  its date by 2 working days, or remitted with a different amount, goes to the inbox. The bank credit is matched by
  UTR (CSV import from the bank or Shiprocket's remittance export).
- **Weight.** Daily `GET /billing/discrepancy` [1]; each one becomes an inbox item due 7 working days after it was
  raised [8], showing our weight and photograph beside the courier's figure; "Dispute" opens Shiprocket's panel with
  the evidence ready (no dispute API found); "Accept" closes it. Prevention: flyers (Delhivery charges flyers by dead
  weight up to 1 kg [49]), real dimensions, `weight_grams` kept right in the catalogue.
- **Returns and exchanges** (a damaged or misprinted copy) are rare: a Shiprocket return order names the customer as
  the pickup and us as the delivery, an exchange order links the two [1]. Until they are frequent, staff create them in
  Shiprocket's panel and the panel records the return AWB on the order.
- **Cost per order.** Daily `GET /account/details/statement` [1] → `ShipmentCharge` rows, idempotent by the
  statement line; the order page shows shipping charged to the customer against freight, COD, RTO and excess-weight
  charges; a monthly report per courier; the wallet balance on the dashboard with a low-balance alert.

### 3.10 Reliability, logs, test mode
- **Retries:** network errors, 429 and 5xx retried by Celery with exponential backoff and jitter (`retry_backoff`,
  `retry_backoff_max`, `retry_jitter`, `max_retries` [90]), as the refund task already does. Tasks are idempotent:
  look before create (find the order by our `order_id` before creating it again). Errors returned with a 200 are
  parsed and treated as failures [1].
- **Circuit breaker** per integration account: open after 5 failures in 5 minutes, one trial call after 5 minutes
  (half-open), closed on success; staff can force it open or reset it [91]. While open, tasks wait instead of calling,
  and the panel says "Shiprocket unavailable since 10:42, 7 calls waiting"; staff can move an order to the manual
  flow.
- **Dead letter:** a task that exhausts its retries writes an `IntegrationFailure` (operation, arguments, attempts,
  last error) and an inbox item; Replay re-runs it, Discard needs a reason. Webhook bodies that fail processing are
  kept and replayable the same way.
- **Timeouts:** 5 s to connect, 20 s to read; 3 s for the live quote.
- **Log:** `IntegrationCall` per call (operation, path, status, duration, the carrier's request id, error, a redacted
  excerpt: phone to its last 4 digits, address to its PIN), kept 90 days; exceptions to Sentry (4.9).
- **Alerts:** no webhook for 24 hours while parcels are moving; a token renewal failing; the wallet below a
  threshold; a circuit open for 30 minutes; COD overdue.
- **Test mode** per integration (off, test, live). Shiprocket "test" is a fake carrier answering from recorded
  fixtures (the Postman collection's examples [1]) for CI and staging; a "live smoke test" button books a prepaid
  order to our own address, assigns an AWB, fetches the label, cancels before pickup and checks the reversal in the
  statement [1][11]. Delhivery tests on its staging host with its test token [31][32]; iThink on `pre-alpha` [81];
  DTDC on its sandbox [84]; India Post during CEPT's test phase [70]. Test orders are marked, as Razorpay test orders
  already are (`Order.livemode`, `is_test`), and never handed to a courier.

### 3.11 Panel screens (Shipping)
- **To book:** packed orders with the suggested courier and price, bulk booking, label printing.
- **Pickups and manifests:** today's pickups, manifest printing, the handover scan.
- **On the way:** filters by status, courier and district; parcels without movement.
- **Exceptions** (in the inbox): failed deliveries, pickup problems, returns on the way, lost parcels, weight
  disputes, each with its deadline.
- **COD:** expected, overdue, remitted, mismatched.
- **Costs:** per order, per courier, per month; the wallet balance.
- **Couriers:** results by district; blocked PINs; the India Post tariff table.
- **Settings → Integrations → Shiprocket:** credentials, pickup locations, webhook URL and token, mode, test
  connection, the log (section 5).

## 4. The other integrations the panel manages

### 4.1 Razorpay
- **Auth and keys.** HTTP Basic with key id and secret; separate test and live pairs; the dashboard shows only the key
  id; a rolled key's predecessor stops "immediately or after 24 hours" [200]. Only Owner and Admin see keys, and
  regenerating needs an OTP [241]. No rate-limit numbers are published: back off on 429 with jitter [201].
- **Orders and capture.** Order states created, attempted, paid (still paid after a refund); a payment not captured
  within the window (default and maximum 3 days) is refunded automatically; a "failed" payment can turn authorised
  for up to 3 days ("late authorisation") [212][213].
- **Refunds.** `POST /v1/payments/:id/refund` with `X-Refund-Idempotency` (10+ characters; a retry must send the same
  body; a concurrent retry gets 409); `speed` normal or `optimum`; states pending, processed, failed; always to the
  original source; a normal refund fails on a payment older than 6 months [214][215][216]. Instant refunds are on by
  default and fall back to normal when impossible; fee per refund ₹7.99 up to ₹1,000, ₹11.99 to ₹25,000, ₹14.99
  above, plus GST; a normal refund costs nothing but the original fee is not returned [217][218][227]. The existing
  refund task finds a lost refund through its notes; the idempotency header is the documented way.
- **Settlements.** `GET /v1/settlements`, `/v1/settlements/:id`, and
  `GET /v1/settlements/recon/combined?year=&month=[&day=]`, whose items (payment, refund, transfer, adjustment) carry `entity_id`, `amount`, `fee`, `tax`,
  `settlement_id`, `settlement_utr`, `order_receipt` [220][221]. `settlement.processed` fires when the transfer
  starts; the bank credit can take 3 hours [210]. Domestic settlement is T+2 working days by the FAQ [224] ("T+1 or
  instant" on the rate card [227]: a conflict). Instant settlement is enabled on request, ₹100 to ₹5 crore, for
  "0.20 - 0.30%" [222][223][226]. Reports can be scheduled daily, weekly or monthly [225].
- **Payment Links** (phone and school orders, already used): `POST /v1/payment_links` with `reference_id` (unique,
  40 characters), `accept_partial`, `expire_by` (at most 6 months), reminders (up to 3, sent only 11:00 to 12:00 and
  15:00 to 17:00), a signed callback; webhooks `payment_link.paid`, `.partially_paid`, `.cancelled`, `.expired`
  [207][228][229][230][231]. Bank transfer on a link (its own account number) is enabled on request [232].
- **Smart Collect** for schools paying by NEFT, RTGS or IMPS: a virtual account ("Customer Identifier") per school
  (`POST /v1/virtual_accounts`), credits reported by `virtual_account.credited` with the UTR and the payer's account;
  version 2.0 adds UPI and real-time settlement but needs a RazorpayX current account at Yes Bank or Axis Bank; not
  for the "Individuals" category; enabled on request; "1% or Rs. 10 per transaction (whichever is lower)" plus GST
  [211][227][233][234][235]. Payers can be restricted to up to 10 known accounts (TPV) [235].
- **Disputes:** `GET /v1/disputes`, `accept`, `contest` with evidence (shipping proof, billing proof) before
  `respond_by`; `payment.dispute.*` webhooks [207][237][238]. The parcel timeline (section 3) is the shipping proof.
- **Webhooks:** `X-Razorpay-Signature` = HMAC-SHA256 of the raw body with the webhook secret; dedupe on
  `x-razorpay-event-id`; at least once, in any order; answer 2xx within 5 s; retried with backoff for 24 hours, then
  the webhook is disabled and an alert email sent, and someone must re-enable it; support can replay an event up to 15
  days old; up to 30 URLs; separate test and live URLs; published source IPs [202]-[209]. The existing handler already
  verifies and deduplicates (`shop/payments.py`); no delivery-log API was found, so webhook health comes from our own
  `WebhookEvent` rows.
- **Test mode:** test cards (e.g. Visa 4100 2800 0000 1007), `success@razorpay` and `failure@razorpay` for UPI
  [239][240].
- **Price** (rate card "Last updated: May 2026"): 2 % per domestic transaction, UPI and RuPay debit included ("Zero
  MDR — 2% platform fee applies"), business cards 2.15 %, international up to 3 %, plus 18 % GST; no setup or annual
  fee [227]. Subscriptions are not needed: ExamLeaf sells one-time purchases.
- **What the panel mirrors** [241]: payment and order search by id or receipt (with the late-authorised case); refunds
  with speed, idempotency key, status and ARN; settlements with the recon drill-down to each order's fee and GST, and
  unmatched items in the inbox; the disputes queue by deadline; payment links (create, resend, cancel); the role split
  Razorpay itself uses (Finance sees settlements and disputes but cannot refund; Support can accept a dispute but not
  refund).

### 4.2 WhatsApp and SMS
- **Meta's pricing:** per delivered template message since 1 July 2025, by category (marketing, utility,
  authentication, authentication-international) and the recipient's country [242]. India, from Meta's own calculator:
  marketing ₹0.8631, utility ₹0.115 (cheaper above 25 million a month), authentication ₹0.115,
  authentication-international ₹2.4971, service ₹0.115 [244]. Free today: replies inside the 24-hour customer service
  window, utility templates inside an open window, 72 hours after an ad click [242]. But Meta's non-template page says
  that from 1 October 2026 service messages and in-window utility templates are charged at the utility rate [243],
  while its main pricing page still calls them free [242]: assume they are charged. Indian accounts must bill in INR
  by 31 December 2026; rates change only on 1 January, April, July or October [242]. GST on Meta's rates: not
  verified.
- **Templates and rules:** utility means non-promotional and tied to the user's own transaction, otherwise Meta files
  it as marketing (and may re-file it with a day's notice) [247]; review within 24 hours; numbered variables that may
  not start or end a template [248]; quality green, yellow or red, with pauses for red [249]. Opt-in is required, may
  be collected on the website, by SMS, IVR or paper, must name the business; opt-outs must be honoured "on or off
  WhatsApp"; a human escalation path is required [250][251]. A new business may reach 250 people a day outside the
  window, 2,000 after business verification, then 10,000, 100,000 and unlimited as quality allows [246].
- **Providers:** MSG91 (the current SMS vendor): ₹500 a month after two free months, plus 18 % GST, and a claim of
  "Zero margin on Meta pricing" not checked against its rate card [253][254]; send with
  `POST /api/v5/whatsapp/whatsapp-outbound-message/bulk/` and the `authkey` header [255]; its webhooks are **unsigned**
  (custom headers allowed), pause on any 4xx except 429, and retry 5xx or 429 at most 5 times [256]. Interakt ₹999 to
  ₹3,799 a month plus taxes and per-message prices about 10 to 39 % above Meta's [257]; Gupshup Meta's price plus
  US$0.001 a message [258]; Wati ₹2,999 to ₹18,499 a month and about 20 to 30 % above Meta [259][260]. Meta's own
  Cloud API has no provider fee and signs webhooks (`X-Hub-Signature-256`), retrying for 7 days [252]. **Choose
  MSG91**: one vendor and one invoice for SMS and WhatsApp, the lowest fixed cost; put a secret in a custom webhook
  header and dedupe on its request id.
- **SMS rules in India (DLT)** [261]-[268]: the business, each sender header (at most 11 characters) and each content
  template are registered on an operator's DLT; one template is linked to one header; templates unused for 90 days are
  deactivated. Categories: transactional (OTPs and the like, within 30 minutes of the customer's action), service
  (about something the customer bought: delivery updates), promotional (opt-out required, DND respected), government.
  "Service explicit" templates were reportedly moved to promotional from 10 March 2026 (a competitor's blog and MSG91,
  not a TRAI text) [268][273]. Since 2025 headers carry a suffix -P, -S, -T or -G (MSG91: from 6 May 2025)
  [261][262][268]. Since 1 October 2024 URLs, APKs and OTT links must be whitelisted [264]. Since the direction of 18
  November 2025 every variable must be typed (`#numeric#`, `#url#`, `#urlott#`, `#cbn#`, `#email#`,
  `#alphanumeric#` up to 40 characters), and untyped templates are rejected after a logging period [265][266]. MSG91's
  Flow API sends by its own template id, which stores the header and the DLT template id [269][270]; its delivery
  webhook carries the DLT template id, a status code and a failure reason such as "Template Id not found on DLT"
  [272]. Price: ₹0.25 to ₹0.16 an SMS by volume, plus 18 % GST [271]; DLT registration about ₹5,900 plus GST per
  operator (vendor document) [274].
- **For the panel:** one template registry: each message (event, channel, language) with its DLT template id, header,
  MSG91 id, WhatsApp template name, category and approval state, typed variables, a test send, delivery reports, and the
  opt-in record (who, when, where) for every WhatsApp number, usually a parent's.

### 4.3 Amazon SES events
- Identity notifications cover only bounces, complaints and deliveries; configuration-set event destinations add
  send, reject, open, click, rendering failure, delivery delay and subscription, to SNS, Firehose, CloudWatch or
  EventBridge; using both duplicates events [275][277][278][288]. Bounces are permanent, transient or undetermined,
  with subtypes such as `OnAccountSuppressionList` [276].
- SNS over HTTPS: the `MessageId` stays the same across retries (dedupe on it) [279]. Verify the signature
  (SignatureVersion 1 is SHA1withRSA, 2 is SHA256withRSA; a topic defaults to 1, so set 2), fetch the certificate only
  from an HTTPS `sns.<region>.amazonaws.com` host, and check the `TopicArn` [280][281]. The default HTTP retry policy
  is 3 attempts 20 s apart; raise it (up to 100 retries within 3,600 s) and add a dead-letter queue [282].
- The account-level suppression list (per Region) adds hard bounces automatically and complaints if chosen; it is
  readable by API [283][284]. Under review at 5 % bounces or 0.1 % complaints; sending may be paused at 10 % or 0.5 %
  [285].
- Price: US$0.10 per 1,000 à la carte; since 2026 also plans (Essentials US$0.16 per 1,000, Pro, Enterprise), and
  accounts idle since June 2025 start on Essentials from 21 July 2026 [286]. Mumbai (`ap-south-1`) endpoints exist
  [287].
- **django-anymail** protects its tracking URL with basic auth, confirms SNS subscriptions itself, **does not verify
  SNS signatures**, and maps delivery delays and subscription events to "unknown" [288][289]. Add the signature check
  (a small function with `cryptography`) or accept basic auth over HTTPS as the control; either way restrict the topic ARN.
- **For the panel:** Mail → Deliverability: bounce and complaint rates against those thresholds, the suppression list
  (ours, which exists as `EmailSuppression`, kept in step with SES's), and each message's events.

### 4.4 Google Workspace sign-in for staff
- OpenID Connect with `openid email profile`; check `iss`, `aud`, `exp`; key the account on `sub`, not the email
  [290]. The `hd` request parameter is only a hint ("client-side requests can be modified"); the server must check
  the `hd` claim of the ID token [290]. An "Internal" consent screen restricts sign-in to the organisation and needs no
  Google verification [292][293][294].
- django-allauth's Google provider verifies the token but has no domain restriction, so `hd` equal to the company's
  Workspace domain and `email_verified` are enforced in a `SocialAccountAdapter.pre_social_login` [296][297]. allauth's MFA stage still runs
  after a Google sign-in for anyone with an authenticator app or a passkey, so the staff MFA rule holds [298][299].
  Workspace's own 2-step verification can be enforced as well; the app cannot see it unless the `amr` claim is
  available, which needs a verified production app [291][295].
- Offboarding: suspending the Workspace account stops new sign-ins, not existing sessions, so the panel's offboarding
  still revokes sessions and keys.

### 4.5 Tally Prime and Zoho Books
- **TallyPrime:** latest 7.1 (20 May 2026); 7.0 (19 December 2025) added JSON import and export; 6.x added none
  [300]-[306]. Every release takes XML over HTTP at `http://<pc>:9000/` (the `Import Data` envelope, `REPORTNAME` Vouchers
  or All Masters, `SVCURRENTCOMPANY`), answering `IMPORTRESULT` or `LINEERROR`; 7.x also takes JSON with headers
  `tallyrequest`, `type`, `id` and `svCurrentCompany` [307]-[311]. The port has no documented authentication, so it
  stays on the office network [309][310]. Exempt books: stock items "Exempt" or "Nil Rated", no tax ledgers; Tally then
  reports them in GSTR-1 Table 8 [313]. Files can be imported with Alt+O (XML always, Excel from 4.0, JSON from 7.0),
  masters first [314]. Tally is also an ODBC server (objects as rows, collections as tables), useful for reading,
  not for posting sales [315]. TallyConnector is a .NET library, not usable from Django [317][318].
- **Zoho Books (India):** `https://www.zohoapis.in/books/v3`, `https://accounts.zoho.in`, OAuth 2.0 (a "Self Client"
  suits a server job), access token 1 hour, refresh token until revoked, `organization_id` on every call; scopes such
  as `ZohoBooks.invoices.CREATE` [320][321][322]. Invoices, contacts, customer payments and credit notes carry
  `gst_treatment`, `gst_no`, `place_of_supply`, `hsn_or_sac`, `tax_id`, and `tax_exemption_id` for exempt items
  [323]-[327]. Limits: 100 requests a minute per organisation; 1,000 to 10,000 a day by plan [320]. Webhooks come from
  workflow rules, signed (`X-Zoho-Webhook-Signature`, HMAC-SHA256), retried 5 times, at most 1,000 a day [328][329].
  India prices billed annually: Standard ₹749, Professional ₹1,499, Premium ₹2,999 a month before tax; free under ₹25
  lakh revenue [330]. Zoho Books also generates e-invoices (Zoho is a GSP) [331][349].
- **Recommendation:** neither is required by law. Start with an export for the accountant (Tally XML, or JSON for
  7.x): sales vouchers by day and series, party ledgers, credit notes, imported with Alt+O. No port is opened. Add a
  live Zoho sync only if the accountant moves to Zoho.

### 4.6 GST: e-invoice, e-way bill, GSTR-1
- **E-invoice (IRN)** applies once aggregate turnover passed ₹5 crore in any preceding year since 2017-18 [338][339];
  aggregate turnover includes exempt supplies, so book sales count (statute read from summaries, not verified). Even
  then it covers only taxable B2B and export invoices and their notes, never bills of supply or B2C sales
  [338][340][352]. The 30-day reporting limit applies only at ₹10 crore or more [341]. Six IRPs, core APIs free
  [336][337]; small taxpayers use a GSP, IRIS or Clear directly, or the free web and GePP tools [337][338][343]. Mechanics:
  auth with an encrypted AppKey returns a token valid 6 hours and a session key [344]; IRN generation returns the
  signed invoice and signed QR [345]; cancel only within 24 hours, never partially, and the number can never be reused
  [346]; the IRN can be fetched only for 3 days, so store the signed invoice and QR [347]; sandbox
  `einv-apisandbox.nic.in` [348]. Published GSP price example: 18 paise an invoice with a 50,000-a-year minimum [351].
  For ExamLeaf: not applicable now; the panel shows turnover against ₹5 crore.
- **E-way bill:** needed above ₹50,000 consignment value [355], but rule 138(14)(e) exempts goods in the Schedule to
  notification 2/2017-CT(Rate), where printed books (HSN 4901) are entry 119, so book-only consignments need none at
  any value [355][357]. Couriers may still ask above ₹50,000 (Delhivery's API makes it mandatory [33]), so the bill of
  supply should carry the exemption reason. Direct e-way bill API access needs about 10,000 bills a month [361].
- **GSTR-1:** JSON sections `b2b`, `b2cl`, `b2cs`, `cdnr`, `cdnur`, `exp`, `at`, `txpd`, `nil`, `hsn`, `doc_issue`
  (from open-source code that follows the GST developer schema, not the official schema) [365]. Exempt books go in
  Table 8 `nil` as `expt_amt`, split intra- or inter-state and registered or unregistered buyer [366][313]. From the
  May 2025 period the HSN table is split into B2B and B2C and Table 13 (documents issued) is mandatory [367][369];
  4-digit HSN suffices up to ₹5 crore turnover [371]; the B2C large-invoice threshold is ₹1 lakh since August 2024
  [367]. Today's `export_gstr1` writes three working CSVs (B2C by place of supply and rate, an HSN summary, credit
  notes) and treats every invoice as B2C, because orders carry no buyer GSTIN (only quotations do): the panel's export
  needs Table 8 for exempt lines, the B2B/B2C HSN split, Table 13, and B2B rows once a school gives a GSTIN.

### 4.7 DigiLocker, for parental consent later
- DPDP Rules 2025 (G.S.R. 846(E), 13 November 2025): rule 10 (verifiable consent of a parent) applies 18 months after
  publication, about 13 May 2027 [380]; a January 2026 proposal to shorten this to 12 months had not been notified by
  September 2026 (law-firm reports) [381][444]. The parent must be an identifiable adult, checked against details the
  business already holds, or details or a "virtual token" from an authorised entity, which includes a Digital Locker
  service provider [380].
- DigiLocker requesters onboard through API Setu: a registered entity (a private company qualifies), vetting and
  approval, signed terms, quarterly usage reports, no separate test environment, no platform charge today, an annual
  audit by a CERT-In-empanelled auditor, data kept in India and nothing stored beyond the transaction unless the law
  requires it [385][386][387][388]. The API is OAuth 2.0 with PKCE (S256); the token answer itself returns name, date
  of birth and gender [383]; Meri Pehchaan (OIDC, v2.4 of September 2026) adds `birthdate` to an ID token [384]. No
  live "age token" service was found [389].
- **For the panel:** store the outcome ("adult verified through DigiLocker on <date>"), not the date of birth.

### 4.8 The PIN directory (data.gov.in)
- Resource `5c2f62fe-5afa-4119-a499-fec9d604d5bd` ("All India Pincode Directory till last month", Department of
  Posts): `circlename`, `regionname`, `divisionname`, `officename`, `pincode`, `officetype`, `delivery`, `district`,
  `statename`, `latitude`, `longitude`; read with
  `GET https://api.data.gov.in/resource/<id>?api-key=&format=json&offset=&limit=&filters[statename]=ASSAM`;
  GODL-India licence [392][393][394]. How often it is refreshed is unclear (a 2022
  snapshot says updated 28 July 2022) [393].
- North-East PIN prefixes (NIC table): Assam 781 to 788, Arunachal 790 to 792, Meghalaya 793 to 794, Manipur 795,
  Mizoram 796, Nagaland 797 to 798, Tripura 799, Sikkim 737 (inside West Bengal's range, so flag by state, not prefix)
  [395].
- **For the panel:** the existing `import_pincodes` gains a page: last import, row count, PINs added and removed, and
  the `delivery` flag shown next to courier serviceability (section 2.4).

### 4.9 Sentry, health checks, uptime
- Already in the code: Sentry starts only with a DSN, with `send_default_pii=False`, no local variables, a scrubbing
  `before_send`, no tracing; `/health/web/` (database, cache, storage) and `/health/` (plus a Celery ping) from
  django-health-check 4.8.0, which supports Django 6.1 [418][419].
- Sentry SaaS: Developer is free but "Limited to one user", so staff need Team, US$26 a month billed annually or US$29
  monthly, with 50,000 errors, 1 cron monitor and 1 uptime monitor included [400]. Data is stored in the US or the EU
  only, chosen once [401]. Cron check-ins (`@sentry_sdk.monitor` with a `monitor_config`) watch the Celery beat jobs;
  automatic beat monitoring is not documented for django-celery-beat's database scheduler [408][409]. Uptime monitors
  check every 1 to 60 minutes and open an issue after three failures [410].
- In India instead: GlitchTip (MIT, same SDK, about 512 MB of RAM, PostgreSQL 14+, uptime and heartbeat monitors)
  [413][414][415][416]; self-hosted Sentry needs 4 CPUs and 16 GB of RAM [411].
- Liveness must not test the database or Celery; readiness and the external uptime check may [418][420]. External
  monitor: Better Stack free (10 monitors and heartbeats, one status page) [422], UptimeRobot free (50 monitors every 5
  minutes, no heartbeats) [423][424], or Uptime Kuma on another machine [421].

### 4.10 Cloudflare R2
- Already in the code: two buckets through django-storages, private files signed for 300 s, public pictures on a
  custom domain, and an option to keep the private bucket on AWS Mumbai.
- Price: Standard US$0.015 per GB-month, US$4.50 per million writes (Class A), US$0.36 per million reads (Class B),
  free egress; free each month 10 GB, 1 million writes, 10 million reads; Infrequent Access US$0.01 per GB-month with
  a 30-day minimum [425].
- Gaps: no ACLs, bucket policies, versioning, object lock or tagging [426]; presigned URLs last at most 7 days and do
  not work on custom domains [427]; lifecycle rules and event notifications to Queues exist [429][430]; jurisdictions
  are only `eu`, `us` and `fedramp` (no India) [432].
- Tokens: Object Read & Write can be limited to one bucket; rolling a token "will invalidate the previous token", so
  rotation means a second token first, then deleting the old one [433][434]; expiry dates and IP filters are available
  [435]. Usage for a meter comes from the GraphQL analytics API [438].

### 4.11 Analytics that do not track children
- The law: "A Data Fiduciary shall not undertake tracking or behavioural monitoring of children or targeted
  advertising directed at children" (DPDP Act s.9(3); a child is under 18) [442]. The exemption for an "educational
  institution" (Fourth Schedule, Part A) covers only its educational activities and children's safety, and no Part B
  purpose covers analytics [380]. Whether ExamLeaf is an educational institution needs a legal view.
- **Umami**: MIT, runs on the existing PostgreSQL, no cookies, the IP only hashed into a session id with a rotating
  salt; set `SALT_ROTATION=day`, never identify users, exclude query strings, and load it only on public pages, never
  in the signed-in course area [446]-[449]. Plausible CE is the alternative (no cookies, daily salt, but ClickHouse and
  2 GB of RAM) [450][451][452]; Matomo needs several settings to stop per-visitor profiles [453]-[456]; PostHog
  self-hosted needs 16 GB and is built around identifying people [458]-[462].

## 5. How others build the integrations page

### 5.1 What the references do
- **Stripe** [463]-[475]: each webhook endpoint lists its event deliveries (Delivered, Pending, Failed) with the HTTP
  result of every attempt and the time of the next one; automatic retries for up to three days in live mode, a few
  hours in test; **Resend** for 15 days; rolling the signing secret either expires the old one now or keeps it valid
  up to 24 hours, signing with both meanwhile; dedupe by event id. API keys: restricted keys with None/Read/Write per
  resource; **Rotate key** with an expiry for the old one (both work up to 7 days); a note of where the key is stored;
  IP restrictions; per-key request logs. Workbench: recent errors, request logs filterable by status, endpoint and
  error, an inspector linking an object to its requests and events; Connect shows each account's outstanding
  requirements and deadlines. Idempotency keys replay the first answer.
- **Shopify** [476]-[482]: declared vs granted scopes (granted ones are queried, not assumed); HMAC-SHA256 of the raw
  body; delivery not guaranteed, so a reconciliation job and a manual re-sync button are expected; 8 retries in 4
  hours, then the subscription is removed; 5-second timeout; the dashboard shows failure rate, p90 response time and 7
  days of delivery logs; a rotated secret coexists with the old one until it is revoked.
- **Zapier** [483]-[488]: a connections list with status (active, expired), **Test connection**, Reconnect, who has
  access and what depends on it; run history with step data, replay of failed runs (automatic at 5 min, 30 min, 1 h,
  3 h, 6 h on paid plans); error emails immediately or as an hourly digest; a workflow that fails in 95 % of more than
  20 runs in 7 days is switched off after a grace period.
- **Svix and Hookdeck** [489]-[499]: retry schedules spelled out (Svix: immediately, 5 s, 5 min, 30 min, 2 h, 5 h,
  10 h, 10 h); an endpoint failing for 5 days is disabled with an event; "recover failed since" and "replay missing";
  failed events kept as a dead-letter list with an issue opened and bulk retry; dedupe windows; a paused connection
  queues events without loss; signing that carries several signatures so secrets can be rotated with a grace period
  (24 hours by default).

### 5.2 The ExamLeaf connections page
One card per integration: Razorpay, Shiprocket (and any manual carrier), MSG91 SMS, MSG91 WhatsApp, Amazon SES,
storage (R2 or S3), Sentry or GlitchTip, Google sign-in; later Zoho, DigiLocker, an e-invoice GSP.
- **Status**: connected, degraded (circuit open, or failures above a threshold), expired (token or credential),
  disabled, not configured; test or live, in different colours, with separate credentials.
- **Last success, last error** (message and HTTP code), an error-rate line over 24 hours and 7 days, p90 latency.
- **Test connection**: one harmless authenticated read per integration (Razorpay: fetch one payment; Shiprocket:
  wallet balance; MSG91: balance; SES: account sending quota; R2: head the bucket), its result kept.
- **Credentials**: masked; replace, never show; created and rotated dates; expiry countdown (Shiprocket's 10-day
  token, our rotation policy); a warning where the provider has no overlap (Delhivery tokens, Cloudflare roll); a note
  of where else the key is configured; every reveal, roll or replace audited.
- **Inbound webhooks**: our URL to paste; the secret or token, rotatable with the previous one accepted for 24 hours;
  received events (accepted, duplicate, rejected, failed) with the raw body for staff with the right; replay one or
  all failed since a time; a silence alarm (no events while some are expected).
- **Outbound calls**: the log per integration (time, operation, status, latency, request id), filterable, linked from
  the order or parcel that caused it; the dead-letter list with Replay and Discard.
- **Scopes**: what the credential may do (Shiprocket API modules and buyer-details access; R2 token scope; the
  Razorpay roles), declared against what the panel needs.
- **Usage and cost**: messages sent and their cost (MSG91, SES), Shiprocket wallet balance and month's freight, R2
  storage and operations against the free tier, Sentry quota; alerts at a spend or balance threshold.
- **Alert rules**: first failure or only after retries are exhausted; immediately or hourly digest; auto-pause after
  sustained failure with an email to the owner.

## 6. Open points

### 6.1 Decisions for the founder
1. Whether ExamLeaf's sample-paper books qualify for Gyan Post: ask the Guwahati postal division in writing. If yes,
   it is the cheapest tracked option for prepaid orders (₹25 for 500 g against ₹54 to ₹70 by courier into the North
   East).
2. Shiprocket plan: Lite now; Business (₹199) once about 50 parcels a month, refunded at 100.
3. Whether an RTO'd order gets a `returned` state, and what a prepaid customer is offered when a parcel comes back
   (reship or refund).
4. Whether WhatsApp is used at all for order updates (opt-in per number, usually a parent's), and on which provider
   (MSG91 recommended).
5. Error reports in the US or EU (Sentry Team, US$26 a month) or in India (GlitchTip on our own machine), given the
   privacy policy's promise.
6. Tally export or Zoho sync: whichever the accountant uses.

### 6.2 Not verified
- Shiprocket: any rate-limit number; the webhook retry schedule; whether label PDF links expire; whether several API
  users can coexist; any API for COD remittance batches, weight disputes or RTO acknowledgement (none found); the
  per-order price of Engage modules.
- Courier zones for parcels within Assam (Zone B or E depends on each courier's rule); rates from one aggregator's
  chart only [86].
- India Post: the 2026 Speed Post parcel tariff; the conflict between [65] and [66] on document rates; whether
  registration can still be bought for Book Post after September 2025; GST on Gyan Post; the bulk-customer API after
  the 2025 software change ([70] is from 2021); India Post COD remittance time.
- Razorpay: published rate limits; T+2 or T+1 settlement; normal-refund timing (5 to 7 or 7 to 10 days).
- WhatsApp: GST on Meta's INR rates; whether service and in-window utility messages are charged from 1 October 2026
  (Meta's two pages disagree); MSG91's real WhatsApp rate card.
- SMS: a TRAI text for moving "service explicit" templates to promotional; DLT fees on the operator portals.
- GST: the statutory definition of aggregate turnover (read from summaries); whether exempt supplies appear in the
  GSTR-1 HSN table and bills of supply in Table 13; Assam's intra-state e-way bill threshold; how Delhivery treats
  exempt goods above ₹50,000.
- DPDP: any amendment of the 18-month timeline after September 2026; a live DigiLocker age token.
- data.gov.in: how often the PIN directory is refreshed.
