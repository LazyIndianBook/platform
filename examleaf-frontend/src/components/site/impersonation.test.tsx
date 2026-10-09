// A support colleague signed in as a customer (the staff console's impersonation): the account manifest's
// `impersonation` read by the layout, the band above every page with End, the actions such a session may not take
// drawn disabled with the reason, and the console's link accepted once on /account/impersonate/.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AddressBook } from "@/components/account/address-book";

import { AcceptImpersonation, ImpersonationBanner, ImpersonationProvider, WhileImpersonated } from "./impersonation";

vi.mock("next/headers", () => ({
  headers: async () => new Headers(),
  cookies: async () => ({ toString: () => "sessionid=s1; csrftoken=c1", has: () => true }),
}));

const VIEWING = { until: "2026-10-09T08:35:00Z", by: "a•••@examleaf.in" }; // 14:05 in India

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const django = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>();
const assign = vi.fn();

beforeEach(() => {
  django.mockReset();
  assign.mockReset();
  vi.stubGlobal("fetch", django);
  vi.stubGlobal("location", { ...window.location, assign });
  document.cookie = "csrftoken=c1"; // the CSRF cookie is there: no config request first
});
afterEach(() => vi.unstubAllGlobals());

describe("the account manifest's impersonation", () => {
  it("is read from account/ with the visitor's cookies, and anything but an answer with it reads as none", async () => {
    const { getImpersonation } = await import("@/lib/api/account");
    django.mockResolvedValueOnce(json(200, { impersonation: VIEWING }));
    expect(await getImpersonation()).toEqual(VIEWING);
    const [url, init] = django.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/account\/$/);
    expect(new Headers(init?.headers).get("Cookie")).toBe("sessionid=s1; csrftoken=c1");

    django.mockResolvedValueOnce(json(200, { impersonation: null }));
    expect(await getImpersonation()).toBeNull();
    django.mockResolvedValueOnce(json(404, { detail: "Not found." })); // the backend without it yet
    expect(await getImpersonation()).toBeNull();
    django.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect(await getImpersonation()).toBeNull();
  });
});

describe("the banner", () => {
  it("is not there for the customer themselves", () => {
    const { container } = render(
      <ImpersonationProvider value={null}>
        <ImpersonationBanner />
      </ImpersonationProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("says who is viewing until when, cannot be dismissed, and End ends the session for the log-in page", async () => {
    render(
      <ImpersonationProvider value={VIEWING}>
        <ImpersonationBanner />
      </ImpersonationProvider>,
    );
    const band = screen.getByRole("region", { name: "A support colleague is viewing this account" });
    expect(band).toHaveTextContent("A support colleague is viewing this account as a•••@examleaf.in until 14:05.");
    expect(band.querySelector("time")).toHaveAttribute("dateTime", VIEWING.until);
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["End"]); // no close, only End

    django.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await userEvent.click(screen.getByRole("button", { name: "End" }));
    const [url, init] = django.mock.calls[0];
    expect(url).toBe("/api/v1/account/impersonate/");
    expect(init?.method).toBe("DELETE");
    expect(new Headers(init?.headers).get("X-CSRFToken")).toBe("c1");
    expect(assign).toHaveBeenCalledWith("/account/login/");
  });

  it("keeps the band and says so when End fails, and takes an impersonation already over as ended", async () => {
    render(
      <ImpersonationProvider value={VIEWING}>
        <ImpersonationBanner />
      </ImpersonationProvider>,
    );
    django.mockResolvedValueOnce(json(503, { detail: "Service unavailable." }));
    await userEvent.click(screen.getByRole("button", { name: "End" }));
    expect(await screen.findByText("That did not work: try End again.")).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();

    django.mockResolvedValueOnce(json(404, { detail: "Not found." })); // expired, or ended from the console
    await userEvent.click(screen.getByRole("button", { name: "End" }));
    expect(assign).toHaveBeenCalledWith("/account/login/");
  });
});

describe("the actions an impersonation may not take", () => {
  it("are drawn disabled with the reason, and left alone for the customer", () => {
    const action = (
      <WhileImpersonated what="Deleting the account">
        <button type="button">Delete my account</button>
      </WhileImpersonated>
    );
    const { rerender } = render(<ImpersonationProvider value={null}>{action}</ImpersonationProvider>);
    expect(screen.getByRole("button", { name: "Delete my account" })).toBeEnabled();
    expect(screen.queryByText(/stays closed/)).toBeNull();

    rerender(<ImpersonationProvider value={VIEWING}>{action}</ImpersonationProvider>);
    expect(screen.getByRole("button", { name: "Delete my account" })).toBeDisabled();
    expect(
      screen.getByText("Deleting the account stays closed while a support colleague is viewing this account."),
    ).toBeInTheDocument();
  });

  it("include the address book: the cards stay, adding, editing and deleting do not", () => {
    const home = {
      id: 1,
      name: "Rahul Das",
      phone: "+919864012345",
      line1: "House 12, Rajgarh Road",
      line2: "Chandmari",
      city: "Guwahati",
      district: "Kamrup Metro",
      state: "AS" as const,
      pin: "781003",
      is_default: true,
      created: "2026-10-01T10:00:00+05:30",
      modified: "2026-10-01T10:00:00+05:30",
    };
    const { rerender } = render(
      <ImpersonationProvider value={VIEWING}>
        <AddressBook addresses={[home]} />
      </ImpersonationProvider>,
    );
    expect(screen.getByRole("article", { name: "Address of Rahul Das, the default one" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Add an address" })).toBeNull();
    expect(screen.getByRole("button", { name: /^Edit/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Delete/ })).toBeDisabled();
    expect(screen.getByText(/^Changing addresses stays closed/)).toBeInTheDocument();

    // an empty book opens the new-address form for the customer, not for an impersonation
    rerender(
      <ImpersonationProvider value={VIEWING}>
        <AddressBook addresses={[]} />
      </ImpersonationProvider>,
    );
    expect(screen.queryByRole("heading", { name: /address/i, level: 2 })).toBeNull();
    expect(screen.queryByLabelText(/^Full name/)).toBeNull();
  });
});

describe("the console's link, /account/impersonate/?token=…", () => {
  it("sends the token once and opens the account", async () => {
    django.mockResolvedValueOnce(json(200, { until: VIEWING.until, user: { id: 7101, email: "r•••@example.com" } }));
    render(
      <StrictMode>
        <AcceptImpersonation token="t-1" />
      </StrictMode>,
    );
    expect(screen.getByRole("heading", { name: "Opening the account" })).toBeInTheDocument();
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("/account/"));
    expect(django).toHaveBeenCalledOnce(); // a development render runs the effect twice: the token goes once
    const [url, init] = django.mock.calls[0];
    expect(url).toBe("/api/v1/account/impersonate/");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"token":"t-1"}');
  });

  it("says honestly that a link expired, was used or is not valid, with the API's words", async () => {
    django.mockResolvedValueOnce(json(400, { token: ["This link has expired."] }));
    render(<AcceptImpersonation token="t-old" />);
    expect(await screen.findByRole("heading", { name: "This link does not open the account" })).toBeInTheDocument();
    expect(screen.getByText("This link has expired.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the home page" })).toHaveAttribute("href", "/");
    expect(assign).not.toHaveBeenCalled();
  });

  it("says the site cannot be reached when the API does not answer", async () => {
    django.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<AcceptImpersonation token="t-1" />);
    expect(await screen.findByRole("heading", { name: "ExamLeaf cannot be reached" })).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
