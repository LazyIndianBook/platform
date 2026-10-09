// THE WORDS OF THE REPORTS, FOR THE STAFF API MOCK (reports.ts): each report's definition and its columns' definitions,
// and the index's lines, copied from examleaf-web's insights/reports.py (the constants the report functions answer
// with), so that "How this is counted" and the hover text are the backend's own. The minimum cell is 10 (5 for the
// course's learners), cash on delivery's terms 10 working days and a grace of 2.
export type Column = { key: string; label: string; definition: string };
export type ReportWords = { definition: string; columns: Column[] };

export const REPORT_WORDS: Record<string, ReportWords> = {
  sales: {
    definition:
      "Sales of the orders placed in the period: paid online, or placed to pay on delivery, and not cancelled or refunded in full since, without test-mode orders. Each line of an order counts in its group; the order's discounts are shared among its lines (the line's own share where it was kept, else in proportion to its value).",
    columns: [
      {
        key: "label",
        label: "Group",
        definition: "What the lines are grouped by: a product, a subject, a class, a board or an edition.",
      },
      {
        key: "period_start",
        label: "Period",
        definition: "The day, the week (it starts on Monday) or the month; the first and the last may be part of one.",
      },
      {
        key: "orders",
        label: "Orders",
        definition: "Orders with a line in the group, each counted once.",
      },
      {
        key: "units",
        label: "Units",
        definition: "Copies (or courses) sold: the quantity of each line.",
      },
      {
        key: "gross",
        label: "Gross (₹)",
        definition: "The lines' selling prices times their quantities, before any discount.",
      },
      {
        key: "discount",
        label: "Discount (₹)",
        definition: "The lines' share of the order's discounts: coupon, offers and a staff discount.",
      },
      {
        key: "net",
        label: "Net (₹)",
        definition:
          "Gross less discount: what the lines sold for. Shipping is not in it and refunds are not taken off: net revenue on Home is the money in, less the money back.",
      },
    ],
  },
  "sales-by-place": {
    definition:
      "Sales of the orders placed in the period, by state, district or PIN code. A state is the place of supply the order was taxed in (its billing state, else the delivery address's); a district is the PIN code's in India Post's directory (else the one typed in the address); a PIN code is the delivery address's. A place with fewer than 10 orders is not shown, and no total counts the places hidden: the rows shown are not the whole of the sales.",
    columns: [
      {
        key: "label",
        label: "Place",
        definition: "A state (the place of supply), a district or a PIN code (where the parcel goes).",
      },
      {
        key: "orders",
        label: "Orders",
        definition: "Orders delivered there, each counted once.",
      },
      {
        key: "units",
        label: "Units",
        definition: "Copies (or courses) sold: the quantity of each line.",
      },
      {
        key: "net",
        label: "Net (₹)",
        definition: "What the lines sold for, after the order's discounts; shipping and refunds not in it.",
      },
    ],
  },
  codes: {
    definition:
      "Book codes by print run: how many were printed, redeemed and (when the course module records them) sold and revoked, and the share redeemed; and the districts the redemptions came from, worked out each night from the redeemer's last order of the subject. A district with fewer than 10 redemptions is not shown.",
    columns: [
      {
        key: "batch",
        label: "Batch",
        definition: "The print run the codes were made for (the label on the books: PHY-2027-1).",
      },
      {
        key: "printed",
        label: "Printed",
        definition: "Codes made for the batch.",
      },
      {
        key: "sold",
        label: "Sold",
        definition:
          "Copies sold of the title the batch is printed in (all the title's batches together), once the course module records which title that is; empty until then.",
      },
      {
        key: "activated",
        label: "Activated",
        definition: "Codes a student has redeemed.",
      },
      {
        key: "activated_7d",
        label: "Last 7 days",
        definition: "Codes redeemed in the last 7 days.",
      },
      {
        key: "revoked",
        label: "Revoked",
        definition: "Codes voided before use, once the course module can void them; empty until then.",
      },
      {
        key: "activation_rate",
        label: "Activation rate",
        definition: "Activated divided by printed.",
      },
    ],
  },
  "course-health": {
    definition:
      "How the revision course is used, by subject and chapter, over complete days, weeks and months (today is not over), worked out each night; staff accounts are left out. A learner counts once in a period however much they did. A cell standing on fewer than 5 learners is not shown. The averages of the daily series count a hidden day as 0; the redemptions by week are of book codes, by subject.",
    columns: [
      {
        key: "label",
        label: "Chapter",
        definition: "A chapter of the course, under its subject.",
      },
      {
        key: "active_7d",
        label: "Active, 7 days",
        definition: "Learners with any activity in the chapter in the 7 days to yesterday.",
      },
      {
        key: "active_28d",
        label: "Active, 28 days",
        definition: "Learners with any activity in the chapter in the 28 days to yesterday, each counted once.",
      },
      {
        key: "clips_started",
        label: "Clips started",
        definition: "Clips whose progress was saved in the 28 days, counted on the day of the last save.",
      },
      {
        key: "clips_completed",
        label: "Clips completed",
        definition: "Of those, the ones watched to the end.",
      },
      {
        key: "completion_rate",
        label: "Clip completion",
        definition: "Completed divided by started.",
      },
      {
        key: "quiz_answers",
        label: "Quiz answers",
        definition: "Quiz questions answered in the 28 days (every try).",
      },
      {
        key: "quiz_accuracy",
        label: "Quiz accuracy",
        definition: "The answers that were right, as a share of the answers.",
      },
      {
        key: "card_reviews",
        label: "Cards turned",
        definition: "Flash cards turned over in the 28 days.",
      },
      {
        key: "card_lapses",
        label: "Lapses",
        definition: "Of those, the cards the learner did not know.",
      },
    ],
  },
  cod: {
    definition:
      "Cash on delivery: the cash couriers collected and have not yet remitted, by how late it is (a remittance is expected 10 working days after delivery and is overdue 2 working days after that), and what was remitted in the period, at the amount expected or another. Parcels of test-mode orders are left out.",
    columns: [
      {
        key: "label",
        label: "Ageing",
        definition: "How late the courier's remittance is: counted from the day it was expected.",
      },
      {
        key: "count",
        label: "Parcels",
        definition: "Parcels delivered whose cash has not come: expected, or overdue.",
      },
      {
        key: "expected",
        label: "Expected (₹)",
        definition: "The cash on delivery amounts of those parcels.",
      },
      {
        key: "oldest_expected_on",
        label: "Oldest expected",
        definition: "The earliest day among them that a remittance was expected.",
      },
    ],
  },
  settlements: {
    definition:
      "Razorpay's settlements: for each, what was paid, the fees and the GST on them, the refunds and what reached the bank, with the bank's UTR; newest first.",
    columns: [
      {
        key: "date",
        label: "Date",
        definition: "The day Razorpay settled.",
      },
      {
        key: "reference",
        label: "Settlement",
        definition: "Razorpay's settlement id.",
      },
      {
        key: "gross",
        label: "Gross (₹)",
        definition: "What the customers paid in the settlement's payments.",
      },
      {
        key: "fees",
        label: "Fees (₹)",
        definition: "Razorpay's fees.",
      },
      {
        key: "tax",
        label: "GST on fees (₹)",
        definition: "The GST Razorpay charged on its fees.",
      },
      {
        key: "refunds",
        label: "Refunds (₹)",
        definition: "The refunds taken off the settlement.",
      },
      {
        key: "net",
        label: "Net (₹)",
        definition: "What reached the bank.",
      },
      {
        key: "utr",
        label: "UTR",
        definition: "The bank's reference of the transfer.",
      },
      {
        key: "state",
        label: "State",
        definition: "Fetched, matched, posted or mismatched.",
      },
    ],
  },
  cohorts: {
    definition:
      "Cohorts of learners by the month their course opened and how, as the share active in each week since, worked out each night while their exam is ahead. A cohort week of fewer than 10 learners shows no shares.",
    columns: [
      {
        key: "cohort_month",
        label: "Cohort",
        definition: "The month the learners' course first opened.",
      },
      {
        key: "source",
        label: "Source",
        definition: "How it opened: a book code, a purchase or a staff grant.",
      },
      {
        key: "week_index",
        label: "Week",
        definition: "Weeks since the course opened (0: the first).",
      },
      {
        key: "n",
        label: "Learners",
        definition: "Learners counted that week, their exam still ahead.",
      },
      {
        key: "active_share",
        label: "Active",
        definition: "The share with any activity that week.",
      },
      {
        key: "churned_share",
        label: "Gone quiet",
        definition: "The share with no activity for 14 days.",
      },
    ],
  },
  forecasts: {
    definition:
      "The demand forecast of the newest night, every district together: copies a week from now to the exam, as the seasonal naive of last season's same week times a growth factor (insights/README.md).",
    columns: [
      {
        key: "title",
        label: "Title",
        definition: "A printed book.",
      },
      {
        key: "week_start",
        label: "Week",
        definition: "The week's Monday.",
      },
      {
        key: "p10",
        label: "P10",
        definition: "Copies: a week in ten sells less.",
      },
      {
        key: "p50",
        label: "P50",
        definition: "Copies: the middle.",
      },
      {
        key: "p90",
        label: "P90",
        definition: "Copies: a week in ten sells more.",
      },
      {
        key: "n",
        label: "Sample",
        definition: "Copies of history the forecast stands on.",
      },
    ],
  },
};

export const REPORT_INDEX: { key: string; label: string; summary: string; page: string; needs: string[] }[] = [
  {
    key: "sales",
    label: "Sales",
    summary: "Units, gross, discount and net by product, subject, class, board or edition, by day, week or month.",
    page: "/reports/sales/",
    needs: ["staff.view_insights", "shop.view_orderitem"],
  },
  {
    key: "sales-by-place",
    label: "Sales by place",
    summary: "Orders, units and net by state, district or PIN code; small places hidden.",
    page: "/reports/place/",
    needs: ["staff.view_insights", "shop.view_orderitem"],
  },
  {
    key: "codes",
    label: "Codes",
    summary: "Book codes printed, sold, activated and revoked by batch, and the districts they were redeemed in.",
    page: "/reports/codes/",
    needs: ["staff.view_insights", "learn.view_bookcode"],
  },
  {
    key: "course-health",
    label: "Course health",
    summary: "Learners, clips, quiz answers and flash cards by subject and chapter, day by day, week by week.",
    page: "/reports/course-health/",
    needs: ["staff.view_insights", "learn.view_progress"],
  },
  {
    key: "cod",
    label: "Cash on delivery",
    summary: "The cash couriers collected and have not remitted, by how late, and what was remitted.",
    page: "/reports/cod/",
    needs: ["staff.view_insights", "staff.view_cod"],
  },
  {
    key: "settlements",
    label: "Settlements",
    summary: "Razorpay's settlements: gross, fees, GST, refunds, net and the UTR.",
    page: "/reports/settlements/",
    needs: ["staff.view_insights", "shop.view_settlement"],
  },
  {
    key: "cohorts",
    label: "Cohorts",
    summary: "Retention by the month the course opened.",
    page: "/reports/cohorts/",
    needs: ["staff.view_insights"],
  },
  {
    key: "forecasts",
    label: "Forecasts",
    summary: "Weekly demand per title with its range.",
    page: "/reports/forecasts/",
    needs: ["staff.view_insights"],
  },
];
