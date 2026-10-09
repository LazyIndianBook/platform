"""Names and lists shared by the hooks (fixture filters), the API and the setup. No frappe import: hooks.py loads this."""

# The tree roots ERPNext's setup wizard makes; after_install makes them first so the fixtures can hang under them.
ROOT_TERRITORY = "All Territories"
ROOT_CUSTOMER_GROUP = "All Customer Groups"
ROOT_ITEM_GROUP = "All Item Groups"

B2C_CUSTOMER = "Online Customers (B2C)"  # every invoice of the website: one customer, no personal data (research 5.8)
B2C_GROUP = "Online B2C"  # ERPNext refuses a customer named like a group; research 4.3 calls it "Online B2C"
B2B_GROUPS = ("School", "Distributor", "Bookseller", "Teacher")
CUSTOMER_GROUPS = (B2C_GROUP, *B2B_GROUPS)

# Assam's districts as the India Post directory spells them, title-cased as the platform's import_pincodes stores them
# (shop.PinCode.districts): the 33 of the directory of December 2021 plus Bajali and Tamulpur (2022). A district the
# directory adds or renames is one line here and in fixtures/…_territory.json (README "Territories").
ASSAM_DISTRICTS = (
    "Bajali", "Baksa", "Barpeta", "Biswanath", "Bongaigaon", "Cachar", "Charaideo", "Chirang", "Darrang", "Dhemaji",
    "Dhubri", "Dibrugarh", "Dima Hasao", "Goalpara", "Golaghat", "Hailakandi", "Hojai", "Jorhat", "Kamrup",
    "Kamrup Metro", "Karbi Anglong", "Karimganj", "Kokrajhar", "Lakhimpur", "Majuli", "Marigaon", "Nagaon", "Nalbari",
    "Sivasagar", "Sonitpur", "South Salmara Mancachar", "Tamulpur", "Tinsukia", "Udalguri", "West Karbi Anglong",
)  # fmt: skip
NORTH_EAST_STATES = ("Arunachal Pradesh", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Sikkim", "Tripura")
TERRITORIES = ("India", "Assam", *ASSAM_DISTRICTS, "North East", *NORTH_EAST_STATES, "Rest of India")

ITEM_GROUP_BY_KIND = {  # shop.Product.Kind
    "sample-papers": "Sample Papers",
    "solutions": "Solutions",
    "bundle": "Bundles",
    "digital": "Digital Courses",
}
ITEM_GROUPS = tuple(ITEM_GROUP_BY_KIND.values())
STOCK_KINDS = ("sample-papers", "solutions")  # printed books: stock items, one Batch per print run

PRICE_LISTS = ("MRP", "School", "Distributor Tier 1", "Distributor Tier 2")
PAYMENT_TERMS = ("Net 15", "Net 30")
MODES_OF_PAYMENT = ("Razorpay", "COD", "UPI", "NEFT/RTGS", "Cheque")

DOC_KINDS = ("tax_invoice", "bill_of_supply", "invoice_cum_bill_of_supply")
PRINT_HEADINGS = {
    "tax_invoice": "Tax Invoice",
    "bill_of_supply": "Bill of Supply",
    "invoice_cum_bill_of_supply": "Invoice-cum-Bill of Supply",
}
CHANNELS = ("web", "staff", "school", "distributor")
NON_TAXABLE_TREATMENTS = ("Exempted", "Nil-Rated", "Non-GST")

ROLES = ("EL Admin", "EL Finance", "EL Packer", "EL Sales", "EL Auditor", "EL Sync")
SYNC_ROLE = "EL Sync"

# The doctypes that carry examleaf_ref (unique, read-only): what the sync writes, or may in future.
REF_DOCTYPES = (
    "Customer", "Address", "Item", "Sales Invoice", "Payment Entry", "Delivery Note", "Journal Entry", "Quotation",
    "Sales Order",
)  # fmt: skip

# The platform's two-letter state codes (django-localflavor, shop.Address.state) to India Compliance's state names
# (india_compliance.gst_india.constants.STATE_NUMBERS); tests/test_setup.py checks every name against that list.
STATE_NAMES = {
    "AN": "Andaman and Nicobar Islands", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam",
    "BR": "Bihar", "CH": "Chandigarh", "CT": "Chhattisgarh", "DH": "Dadra and Nagar Haveli and Daman and Diu",
    "DL": "Delhi", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep Islands",
    "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur", "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland",
    "OR": "Odisha", "PY": "Puducherry", "PB": "Punjab", "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu",
    "TG": "Telangana", "TR": "Tripura", "UP": "Uttar Pradesh", "UT": "Uttarakhand", "WB": "West Bengal",
}  # fmt: skip

SHIPPING_ITEM = "EL-SHIPPING"  # the delivery charge's line: a composite supply, so it takes the goods' HSN and rate
