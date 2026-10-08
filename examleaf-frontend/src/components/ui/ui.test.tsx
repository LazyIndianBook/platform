// A render test for each component of the design system (components.md): what a screen reader and a keyboard
// meet, and the states the spec asks for.
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";

import { Accordion } from "./accordion";
import { Alert } from "./alert";
import { Badge, BadgeLink, STATUS_VARIANT } from "./badge";
import { Band, Marker, NightBand, QRule } from "./band";
import { Breadcrumb } from "./breadcrumb";
import { Button, buttonVariants } from "./button";
import { Card, CardContent, CardFooter, CardHeader, CardLink, CardTitle } from "./card";
import { Checkbox, Radio, SelectableCard, Switch } from "./choice";
import { CoverPicture, NoCover } from "./cover";
import { CoverStage } from "./cover-stage";
import { Dialog, DialogBody, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTrigger } from "./dialog";
import { Drawer } from "./drawer";
import { EmptyState } from "./empty-state";
import { Field, FieldLegend, FieldSet } from "./field";
import { Input, InputPrefix, Textarea } from "./input";
import { OtpInput } from "./input-otp";
import { Select } from "./native-select";
import { Pagination, pageWindow } from "./pagination";
import { Price } from "./price";
import { Progress } from "./progress";
import { QrCard } from "./qr-card";
import { Skeleton } from "./skeleton";
import { Stepper } from "./stepper";
import { SubjectTile } from "./subject-tile";
import { Table, TableCell, TableHead } from "./table";
import { Tabs } from "./tabs";
import { Timeline } from "./timeline";
import { toast, Toaster } from "./toaster";

describe("Button", () => {
  it("renders its variant and size; busy, it ignores presses but keeps the focus (accessibility review F1)", async () => {
    const press = vi.fn();
    const { rerender } = render(
      <>
        <Button variant="accent" size="lg">
          Buy the books
        </Button>
        <Button onClick={press}>Pay</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Buy the books" })).toHaveClass("bg-accent", "min-h-[52px]");
    const pay = screen.getByRole("button", { name: "Pay" });
    pay.focus();
    rerender(
      <>
        <Button variant="accent" size="lg">
          Buy the books
        </Button>
        <Button onClick={press} busy>
          Pay
        </Button>
      </>,
    );
    expect(pay).toHaveAttribute("aria-busy", "true");
    expect(pay).toHaveAttribute("aria-disabled", "true");
    expect(pay).not.toBeDisabled();
    expect(pay).toHaveFocus();
    await userEvent.click(pay);
    expect(press).not.toHaveBeenCalled();
  });

  it("busy, a form's submit button sends nothing, pressed or by Enter in a field", async () => {
    const sent = vi.fn((event: React.FormEvent) => event.preventDefault());
    const form = (busy: boolean) => (
      <form onSubmit={sent}>
        <label>
          Email <input name="email" />
        </label>
        <Button type="submit" busy={busy}>
          Save
        </Button>
      </form>
    );
    const { rerender } = render(form(true));
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toHaveAttribute("aria-busy", "true");
    expect(save).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(save);
    await userEvent.type(screen.getByRole("textbox", { name: "Email" }), "ananya@example.com{Enter}");
    expect(sent).not.toHaveBeenCalled();
    rerender(form(false)); // the same presses send it once it is no longer busy
    await userEvent.type(screen.getByRole("textbox", { name: "Email" }), "{Enter}");
    await userEvent.click(save);
    expect(sent).toHaveBeenCalledTimes(2);
  });

  it("disabled, it ignores presses and says so", async () => {
    const press = vi.fn();
    render(
      <Button disabled onClick={press}>
        Buy the books
      </Button>,
    );
    const buy = screen.getByRole("button", { name: "Buy the books" });
    expect(buy).toBeDisabled();
    expect(buy).not.toHaveAttribute("aria-busy");
    await userEvent.click(buy);
    expect(press).not.toHaveBeenCalled();
  });

  it("styles a link as a button, the caller's classes winning", () => {
    expect(buttonVariants({ variant: "secondary", className: "w-full" })).toContain("w-full");
    expect(buttonVariants({ variant: "secondary" })).not.toContain("border-transparent");
  });
});

describe("Badge", () => {
  it("carries tiers and subjects in words and colour", () => {
    render(
      <>
        <Badge variant="hard">Hard</Badge>
        <Badge variant="physics">Physics</Badge>
        <BadgeLink href="/books/chemistry-2027/" variant="chemistry">
          Chemistry
        </BadgeLink>
      </>,
    );
    expect(screen.getByText("Hard")).toHaveClass("bg-hard");
    expect(screen.getByText("Physics")).toHaveClass("subject-physics");
    expect(screen.getByRole("link", { name: "Chemistry" })).toHaveClass("min-h-11");
  });

  it("draws an order's status as the board lists them: cancelled an outline, refunded on paper 2", () => {
    render(
      <>
        <Badge variant={STATUS_VARIANT.pending}>Awaiting payment</Badge>
        <Badge variant={STATUS_VARIANT.shipped}>Shipped</Badge>
        <Badge variant={STATUS_VARIANT.cancelled}>Cancelled</Badge>
        <Badge variant={STATUS_VARIANT.refunded}>Refunded</Badge>
      </>,
    );
    expect(screen.getByText("Awaiting payment")).toHaveClass("text-gold-text", "font-mono");
    expect(screen.getByText("Shipped")).toHaveClass("bg-medium");
    expect(screen.getByText("Cancelled")).toHaveClass("bg-transparent");
    expect(screen.getByText("Refunded")).toHaveClass("bg-paper-2");
  });
});

describe("Alert", () => {
  it("is a status by default and an alert for an error summary", () => {
    render(
      <>
        <Alert title="Payment received">Thank you.</Alert>
        <Alert variant="error" role="alert" title="There is a problem" />
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Payment received");
    expect(screen.getByRole("alert")).toHaveTextContent("There is a problem");
  });

  it("says a success in its title and words, in its tint, the icon hidden from screen readers", () => {
    render(
      <Alert variant="success" title="Payment received">
        <p>Razorpay confirmed ₹339.00. We email the invoice when the order is packed.</p>
      </Alert>,
    );
    const news = screen.getByRole("status");
    expect(news).toHaveClass("bg-success-bg", "border-success-line");
    expect(news).toHaveTextContent("Payment received");
    expect(news).toHaveTextContent("Razorpay confirmed ₹339.00.");
    expect(news.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Card", () => {
  it("has a header, body and footer, and a card link is one link", () => {
    render(
      <>
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent>Body</CardContent>
          <CardFooter>Footer</CardFooter>
        </Card>
        <CardLink href="/s/PHY-E01/">E-01</CardLink>
      </>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Summary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "E-01" })).toHaveAttribute("href", "/s/PHY-E01/");
  });
});

describe("Field and controls", () => {
  it("links the label, the help and the error to the control", () => {
    render(
      <Field id="pin" label="PIN code" required help="6 digits, such as 781001." error="Enter the 6-digit PIN code.">
        <Input inputMode="numeric" />
      </Field>,
    );
    const input = screen.getByLabelText(/PIN code/);
    expect(input).toBeRequired();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("6 digits, such as 781001. Enter the 6-digit PIN code.");
    // the message itself is the field's own line, tied to the control by its id
    expect(input.getAttribute("aria-describedby")?.split(" ")).toContain("pin-error");
    expect(document.getElementById("pin-error")).toHaveTextContent("Enter the 6-digit PIN code.");
    expect(document.getElementById("pin-error")?.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("leaves a valid field unmarked", () => {
    render(
      <Field id="email" label="Email address" help="We send the code here.">
        <Input type="email" />
      </Field>,
    );
    const input = screen.getByLabelText("Email address");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).toHaveAttribute("aria-describedby", "email-help");
  });

  it("renders the input, textarea, prefixed input and native select", () => {
    render(
      <>
        <label>
          Notes <Textarea />
        </label>
        <label>
          Mobile <InputPrefix prefix="+91" type="tel" />
        </label>
        <label>
          Class{" "}
          <Select defaultValue="12">
            <option value="12">Class 12</option>
          </Select>
        </label>
      </>,
    );
    expect(screen.getByRole("textbox", { name: "Notes" })).toHaveClass("min-h-24");
    expect(screen.getByRole("textbox", { name: "Mobile" })).toHaveAttribute("type", "tel");
    expect(screen.getByRole("combobox", { name: /Class/ })).toHaveValue("12");
  });

  it("has native checkbox, radio, switch and selectable card", async () => {
    render(
      <>
        <Checkbox name="consent">I agree</Checkbox>
        <Radio name="pay" value="upi">
          UPI
        </Radio>
        <Switch name="sms">Order updates by SMS</Switch>
        <SelectableCard name="address" value="1">
          Home
        </SelectableCard>
      </>,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "I agree" }));
    expect(screen.getByRole("checkbox", { name: "I agree" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "UPI" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Order updates by SMS" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Home" })).toBeInTheDocument();
  });

  it("numbers a fieldset's legend", () => {
    render(
      <FieldSet>
        <FieldLegend number={1}>About you</FieldLegend>
      </FieldSet>,
    );
    expect(screen.getByRole("group", { name: /About you/ })).toBeInTheDocument();
  });
});

describe("OtpInput", () => {
  it("is one numeric field of six digits that the phone can fill from an SMS", () => {
    render(<OtpInput />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("inputmode", "numeric");
    expect(input).toHaveAttribute("maxlength", "6");
  });

  it("fills all six boxes from a pasted code, spaces dropped, and a whole code replaces a typed digit", async () => {
    // input-otp looks for a password manager's badge once the field has focus; jsdom has no elementFromPoint
    Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
    const { container } = render(<OtpInput />);
    const input = screen.getByRole("textbox");
    const boxes = () => [...container.querySelectorAll('[data-slot="otp-box"]')].map((box) => box.textContent);
    act(() => input.focus());
    await userEvent.paste("482 913");
    expect(input).toHaveValue("482913");
    expect(boxes()).toEqual(["4", "8", "2", "9", "1", "3"]);
    await userEvent.clear(input);
    await userEvent.keyboard("7");
    expect(input).toHaveValue("7");
    await userEvent.paste("Your code: 105226");
    expect(input).toHaveValue("105226");
  });
});

describe("Skeleton, Table, Breadcrumb, Pagination, Stepper", () => {
  it("keeps a skeleton still (no shimmer, no pulse) and out of the accessibility tree", () => {
    const { container } = render(<Skeleton className="w-40" />);
    const skeleton = container.firstChild as HTMLElement;
    expect(skeleton).toHaveAttribute("aria-hidden", "true");
    expect(skeleton).toHaveClass("bg-paper-2");
    expect(skeleton.className).not.toMatch(/animate|pulse|shimmer|transition/);
  });

  it("gives a table its caption and right-aligns numbers", () => {
    render(
      <Table caption="Marking steps">
        <thead>
          <tr>
            <TableHead>Step</TableHead>
            <TableHead numeric>Marks</TableHead>
          </tr>
        </thead>
        <tbody>
          <tr>
            <TableCell>P = VI</TableCell>
            <TableCell numeric>1</TableCell>
          </tr>
        </tbody>
      </Table>,
    );
    expect(screen.getByRole("table", { name: "Marking steps" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Marks" })).toHaveClass("num");
  });

  it("marks the current page of a breadcrumb", () => {
    render(<Breadcrumb trail={[{ label: "Home", href: "/" }, { label: "Physics" }]} />);
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByText("Physics")).toHaveAttribute("aria-current", "page");
  });

  it("paginates with the current page marked and the ends disabled", () => {
    expect(pageWindow(5, 10)).toEqual([1, "…", 4, 5, 6, "…", 10]);
    const { unmount } = render(<Pagination page={1} pages={3} href={(n) => `?page=${n}`} />);
    expect(screen.getByText("1")).toHaveAttribute("aria-current", "page");
    // the arrows keep their words for screen readers; at the first page Previous is a disabled span, not a link
    expect(screen.getByText("Previous").closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByRole("link", { name: "Previous" })).toBeNull();
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", "?page=2");
    expect(screen.getByRole("link", { name: "Page 2" })).toHaveAttribute("href", "?page=2");
    unmount();
    render(<Pagination page={3} pages={3} href={(n) => `?page=${n}`} />);
    expect(screen.getByText("Next").closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "?page=2");
  });

  it("says which checkout step is current and links back to done ones", () => {
    render(
      <Stepper
        label="Checkout"
        current={1}
        steps={[
          { label: "Address", href: "/checkout/" },
          { label: "Delivery" },
          { label: "Payment" },
          { label: "Done" },
        ]}
      />,
    );
    expect(screen.getByRole("list", { name: "Checkout" })).toBeInTheDocument();
    expect(screen.getByText("2. Delivery").closest("[aria-current]")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("link", { name: /1\. Address/ })).toHaveAttribute("href", "/checkout/");
  });

  it("says progress in words beside the bar, and to screen readers as the bar's value", () => {
    render(<Progress value={12} max={48} label="12 of 48 clips" name="Clips watched" />);
    const bar = screen.getByRole("progressbar", { name: "Clips watched" });
    expect(bar).toHaveAttribute("aria-valuenow", "12");
    expect(bar).toHaveAttribute("aria-valuemax", "48");
    expect(bar).toHaveAttribute("aria-valuetext", "12 of 48 clips");
    expect(screen.getByText("12 of 48 clips")).toBeInTheDocument();
    expect((bar.firstElementChild as HTMLElement).style.width).toBe("25%");
  });
});

describe("Tabs, Accordion, Dialog, Drawer, Toaster", () => {
  it("makes radio-based tabs with the first checked", () => {
    render(
      <Tabs
        name="subject"
        legend="Subject"
        options={[
          { value: "all", label: "All subjects" },
          { value: "physics", label: "Physics" },
        ]}
      />,
    );
    expect(screen.getByRole("radio", { name: "All subjects" })).toBeChecked();
  });

  it("moves between tabs with the arrow keys, as a radio group does", async () => {
    render(
      <Tabs
        name="subject"
        legend="Subject"
        options={[
          { value: "all", label: "All subjects" },
          { value: "PHY", label: "Physics" },
          { value: "CHE", label: "Chemistry" },
        ]}
      />,
    );
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: "All subjects" })).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Physics" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Physics" })).toHaveFocus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "All subjects" })).toBeChecked();
    expect(screen.getByRole("group", { name: "Subject" })).toBeInTheDocument();
  });

  it("opens an accordion item natively, its + / − sign hidden from screen readers", () => {
    const { container } = render(
      <Accordion summary="Are the solutions really free?" open>
        <p>Yes.</p>
      </Accordion>,
    );
    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText("Are the solutions really free?")).toBeInTheDocument();
    expect(container.querySelector("summary")).toHaveTextContent(/^Are the solutions really free\?$/);
    expect(container.querySelector("summary [data-sign]")).toHaveAttribute("aria-hidden", "true");
  });

  it("opens a dialog on its safe button and gives focus back to what opened it (accessibility review F6)", async () => {
    render(
      <Dialog>
        <DialogTrigger>Remove</DialogTrigger>
        <DialogContent aria-describedby={undefined}>
          <DialogHeader>Remove this book?</DialogHeader>
          <DialogBody>It leaves your cart.</DialogBody>
          <DialogFooter>
            <DialogClose asChild>
              <Button>Keep it</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );
    const opener = screen.getByRole("button", { name: "Remove" });
    await userEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Remove this book?" });
    expect(within(dialog).getByRole("button", { name: "Keep it" })).toHaveFocus();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep it" }));
    expect(dialog).not.toHaveAttribute("open");
    expect(opener).toHaveFocus();
    // a click inside the box keeps it open (its padding too); a click on the backdrop closes it, focus back again
    await userEvent.click(opener);
    expect(dialog).toHaveAttribute("open");
    fireEvent.click(within(dialog).getByText("It leaves your cart."));
    fireEvent.click(dialog.firstElementChild!);
    expect(dialog).toHaveAttribute("open");
    fireEvent.click(dialog);
    expect(dialog).not.toHaveAttribute("open");
    expect(opener).toHaveFocus();
  });

  it("opens the menu drawer with aria-expanded and closes it with Escape, focus back on Menu", async () => {
    render(
      <Drawer id="site-menu" label="Menu">
        <a href="#shop">Shop</a>
      </Drawer>,
    );
    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveAttribute("data-open", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();
  });

  it("lets Tab go from Menu into the open menu, and closes it when focus leaves (accessibility review F3)", async () => {
    render(
      <>
        <Drawer id="site-menu" label="Menu">
          <a href="#shop">Shop</a>
        </Drawer>
        <a href="#main">Buy the books</a>
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Shop" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Buy the books" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("shows a toast for 6 s in a labelled live region, paused while hovered, dismissible (F4, F13)", async () => {
    vi.useFakeTimers();
    render(<Toaster />);
    const region = screen.getByRole("region", { name: "Messages" });
    expect(region).toHaveAttribute("aria-live", "polite"); // in the page before any message
    act(() => toast.success("ExamLeaf Chemistry Sample Papers 2027 is in your cart."));
    const message = screen.getByText(/is in your cart/);
    act(() => vi.advanceTimersByTime(5000));
    expect(message).toBeInTheDocument(); // at least 5 s
    fireEvent.pointerEnter(message.closest("li")!);
    act(() => vi.advanceTimersByTime(20000));
    expect(message).toBeInTheDocument(); // held while the pointer is on it
    fireEvent.pointerLeave(message.closest("li")!);
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.queryByText(/is in your cart/)).toBeNull();
    act(() => toast.success("Your details are saved."));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Your details are saved.")).toBeNull();
    vi.useRealTimers();
  });
});

describe("Site pieces", () => {
  it("draws a subject tile as one link with its facts", () => {
    render(
      <SubjectTile subject="maths" name="Mathematics" href="/books/mathematics-2027/" marks={80} time="3 hours" />,
    );
    const tile = screen.getByRole("link", { name: /Mathematics/ });
    expect(tile).toHaveClass("tile", "subject-maths");
    expect(tile).toHaveTextContent("80 marks · 3 hours");
  });

  it("fans four covers, the first one a priority image with AVIF and WebP sizes", () => {
    const books = ["physics", "chemistry", "mathematics", "biology"].map((name) => ({
      href: `/books/${name}-2027/`,
      cover: `http://localhost:3000/static/img/${name}.png`,
      title: name,
    }));
    const { container } = render(<CoverStage books={books} />);
    expect(screen.getAllByRole("link")).toHaveLength(4);
    const images = container.querySelectorAll("img");
    expect(images[0]).toHaveAttribute("fetchpriority", "high");
    expect(images[1]).toHaveAttribute("loading", "lazy");
    expect(container.querySelector('source[type="image/avif"]')).toHaveAttribute(
      "srcset",
      // 240w: a phone's 104 px box at 1.75x takes it (Lighthouse review L5)
      "http://localhost:3000/static/img/physics-240.avif 240w, http://localhost:3000/static/img/physics-320.avif 320w, http://localhost:3000/static/img/physics-480.avif 480w",
    );
  });

  it("draws a product picture as it is and a missing cover in the subject's colours", () => {
    const { container } = render(
      <>
        <CoverPicture src="https://media.examleaf.in/p/1.png" alt="Cover" sizes="200px" />
        <NoCover subject="biology" name="Biology" kind="Solutions" />
      </>,
    );
    expect(container.querySelector("picture")).toBeNull();
    expect(screen.getByText("Biology").closest("[aria-hidden]")).toHaveClass("subject-biology");
  });

  it("prints a price without zero paise, the MRP struck through and the saving in words", () => {
    render(<Price price="499.00" mrp="548.00" />);
    expect(screen.getByText("₹499")).toBeInTheDocument();
    expect(screen.getByText("MRP").parentElement?.tagName).toBe("S");
    expect(screen.getByText("Save ₹49 (9%)")).toBeInTheDocument();
  });

  it("shows an empty state with its heading level and one action", () => {
    render(
      <EmptyState
        title="We could not find that page"
        headingLevel={1}
        eyebrow="Error 404"
        action={<a href="#books">See the books</a>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "We could not find that page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the books" })).toBeInTheDocument();
  });

  it("marks the current step of an order's timeline", () => {
    render(
      <Timeline
        items={[
          { label: "Ordered", state: "done", time: "8 Oct 2026, 10:42" },
          { label: "Packed", state: "current" },
          { label: "Shipped", state: "upcoming", note: "We email you the tracking number." },
        ]}
      />,
    );
    expect(screen.getByText("Packed").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("titles the QR card as the page's heading with the marks", () => {
    render(
      <QrCard
        subject="physics"
        subjectName="Physics"
        tier="M"
        code="PHY-M04"
        eyebrow="Sample Paper M-04 · Medium · ASSEB Class 12"
        title="Physics: solutions"
        facts={[{ label: "Full marks", value: 70 }]}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Physics: solutions" })).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getByText("70")).toBeInTheDocument();
  });

  it("puts a band in the night colours and numbers a section", () => {
    const { container } = render(
      <>
        <NightBand>
          <QRule number={1} label="What's inside" />
        </NightBand>
        <Band>
          <Marker draw>the solutions free</Marker>
        </Band>
      </>,
    );
    expect(container.querySelector("section")).toHaveClass("band-night");
    expect(screen.getByText("Q.1")).toBeInTheDocument();
    // Direction A: the one emphasis of a view is red ink in italics, no drawn highlighter
    expect(screen.getByText("the solutions free")).toHaveClass("marker");
  });

  it("keeps the header on one row with the cart count spoken and the menu button", () => {
    render(<SiteHeader signedIn={false} cartCount={2} />);
    expect(screen.getByRole("link", { name: "Cart, 2 books" })).toHaveAttribute("href", "/cart/");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-controls", "site-menu");
    // the current page is kept as the destination of Log in (coverage matrix G15)
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/account/login/?next=%2Fbooks%2Fphysics-2027%2F",
    );
  });

  it("lists the books and the shop links in the footer", () => {
    render(<SiteFooter books={[{ href: "/books/physics-2027/", name: "Physics" }]} signedIn />);
    expect(screen.getByRole("link", { name: "Physics" })).toHaveAttribute("href", "/books/physics-2027/");
    expect(screen.getByRole("link", { name: "My orders" })).toBeInTheDocument();
  });
});
