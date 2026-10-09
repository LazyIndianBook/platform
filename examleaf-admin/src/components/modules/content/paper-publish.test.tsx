// A paper on the site or off it, and the book's open sample: taking it off is typed (its code), putting it back and
// the open sample are one press, each through POST …/publish/.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type ContentPaperDetail, publishPaper } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { navigation } from "@/test/navigation";

import { PaperPublish } from "./paper-publish";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  publishPaper: vi.fn(),
}));

const words = copy.content.papers;

const paper = (row: Partial<ContentPaperDetail> = {}): ContentPaperDetail => ({
  id: 2201,
  code: "PHY-E01",
  title: "Physics Sample Paper E-01",
  book: 2101,
  book_title: "ExamLeaf Physics Sample Papers 2027",
  subject_code: "PHY",
  tier: "E",
  number: 1,
  full_marks: 70,
  pass_marks: 21,
  time_text: "3 hours",
  is_published: true,
  is_sample: false,
  questions: 3,
  drafts: 0,
  header_json: { lines: [], allotment: [] },
  tree: [],
  ...row,
});

beforeEach(() => {
  vi.mocked(publishPaper).mockReset();
  vi.mocked(publishPaper).mockResolvedValue(paper() as never);
  navigation.router.refresh = vi.fn();
});

describe("PaperPublish", () => {
  it("makes it the open sample in one press, and stops it being one", async () => {
    const { unmount } = render(<PaperPublish paper={paper()} />);
    await userEvent.click(screen.getByRole("button", { name: words.makeSample }));
    expect(publishPaper).toHaveBeenCalledWith(2201, { is_sample: true });
    expect(navigation.router.refresh).toHaveBeenCalled();
    unmount();
    render(<PaperPublish paper={paper({ is_sample: true })} />);
    await userEvent.click(screen.getByRole("button", { name: words.unsample }));
    expect(publishPaper).toHaveBeenLastCalledWith(2201, { is_sample: false });
  });

  it("takes it off the site only once its code is typed", async () => {
    render(<PaperPublish paper={paper()} />);
    await userEvent.click(screen.getByRole("button", { name: words.unpublish }));
    const dialog = screen.getByRole("dialog");
    const confirm = dialog.querySelector<HTMLButtonElement>("button[type=submit]")!;
    await userEvent.click(confirm);
    expect(publishPaper).not.toHaveBeenCalled();
    await userEvent.type(screen.getByRole("textbox", { name: copy.confirmTyped.instruction("PHY-E01") }), "PHY-E01");
    await userEvent.click(confirm);
    expect(publishPaper).toHaveBeenCalledWith(2201, { is_published: false });
  });

  it("puts an unpublished paper back in one press", async () => {
    render(<PaperPublish paper={paper({ is_published: false })} />);
    expect(screen.queryByRole("button", { name: words.makeSample })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: words.publish }));
    expect(publishPaper).toHaveBeenCalledWith(2201, { is_published: true });
  });
});
