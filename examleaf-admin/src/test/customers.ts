// Test data for the customers module's unit tests (Vitest only): a customer as GET users/ and GET users/{id}/ answer
// it, with the parts a test changes.
import type { Customer, CustomerDetail } from "@/lib/api/staff";

export function customerWith(extra: Partial<Customer> = {}): Customer {
  return {
    id: 7102,
    email: "bi•••@example.com",
    phone: "••••••1873",
    full_name: "Bikash Deka",
    class_level: null,
    board: "",
    district: "Kamrup Metro",
    under_18: false,
    status: "active",
    consent: "adult",
    email_verified: true,
    login_phone_verified: true,
    created: "2026-06-12T06:00:00Z",
    last_login: "2026-10-09T05:00:00Z",
    age_band: "adult",
    consent_method: "",
    teacher: "none",
    mfa_on: false,
    locked: false,
    ...extra,
  };
}

/** A student under 18 whose parent has not confirmed. */
export function childWith(extra: Partial<CustomerDetail> = {}): CustomerDetail {
  return detailWith({
    id: 7104,
    full_name: "Arjun Baruah",
    email: "ar•••@example.com",
    phone: "",
    under_18: true,
    age_band: "13_17",
    consent: "pending",
    login_phone_verified: false,
    parent_contact: "••••••4410",
    parent_link: {
      sent: 2,
      last_at: "2026-10-08T10:00:00Z",
      expires_at: "2026-10-15T10:00:00Z",
      expired: false,
      today: 1,
      daily_limit: 3,
    },
    ...extra,
  });
}

export function detailWith(extra: Partial<CustomerDetail> = {}): CustomerDetail {
  return {
    ...customerWith(),
    roles: ["STUDENT"],
    mfa: [],
    parent_contact: "",
    orders: [],
    consents: [],
    sessions: [],
    deletion_due_at: null,
    parent_link: null,
    linked: [],
    ...extra,
  };
}
