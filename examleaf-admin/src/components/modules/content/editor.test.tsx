// The content editor: a formula KaTeX cannot draw is named with its line and nothing is sent; a save writes the draft,
// and the API's own refusal goes beside its field; the saved draft is submitted, never while changes are unsaved;
// without the change permission the text is read only; what was typed and not saved is offered back.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManifestProvider } from "@/components/shell/manifest";
import { ApiError } from "@/lib/api/errors";
import { type ContentSolution, draftAction, updateSolution } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";
import { manifestWith } from "@/test/fixtures";
import { navigation } from "@/test/navigation";

import { Editor } from "./editor";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  updateSolution: vi.fn(),
  draftAction: vi.fn(),
}));

const words = copy.content.editor;

const solution = (row: Partial<ContentSolution> = {}): ContentSolution => ({
  id: 2402,
  question: 2302,
  question_label: "2(c)",
  paper: 2201,
  paper_code: "PHY-E01",
  state: "published",
  preview: "",
  question_text: "Find the current.",
  marks_text: "2",
  body_md: "$I = 0.5$ A",
  draft: {},
  draft_by: null,
  published_at: null,
  published_by: null,
  review: null,
  ...row,
});

function renderEditor(record = solution(), permissions = [P.solutionsView, P.solutionsChange]) {
  return render(
    <ManifestProvider manifest={manifestWith(permissions)}>
      <Editor kind="solutions" record={record} />
    </ManifestProvider>,
  );
}

async function replaceText(text: string) {
  const box = screen.getByRole("textbox", { name: words.source });
  await userEvent.clear(box);
  await userEvent.click(box);
  await userEvent.paste(text);
  return box;
}

beforeEach(() => {
  vi.mocked(updateSolution).mockReset();
  vi.mocked(draftAction).mockReset();
  navigation.router.refresh = vi.fn();
  window.sessionStorage.clear();
});

describe("Editor", () => {
  it("names a formula KaTeX cannot draw, with its line, and sends nothing", async () => {
    renderEditor();
    await replaceText("Step one\n$\\frac{1}{2$ A");
    await userEvent.click(screen.getByRole("button", { name: words.save }));
    expect(screen.getByText(words.mathTitle)).toBeVisible();
    expect(screen.getByText(/^Line 2: /)).toBeVisible();
    expect(updateSolution).not.toHaveBeenCalled();
  });

  it("saves the draft; the API's refusal goes beside the field, and a save that works draws the page again", async () => {
    vi.mocked(updateSolution)
      .mockRejectedValueOnce(
        new ApiError(400, "invalid", "Line 1: a link is not allowed here.", {
          body_md: ["Line 1: a link is not allowed here."],
        }),
      )
      .mockResolvedValueOnce(solution() as never);
    renderEditor();
    await replaceText("$I = \\dfrac{6}{12} = 0.50$ A");
    expect(screen.getByText(words.unsaved)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: words.save }));
    expect(updateSolution).toHaveBeenCalledWith(2402, "$I = \\dfrac{6}{12} = 0.50$ A");
    expect((await screen.findAllByText("Line 1: a link is not allowed here.")).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: words.save }));
    await waitFor(() => expect(navigation.router.refresh).toHaveBeenCalled());
  });

  it("submits a saved draft for review, but not while changes are unsaved", async () => {
    vi.mocked(draftAction).mockResolvedValueOnce({} as never);
    renderEditor(solution({ state: "draft", draft: { body_md: "$I = 0.50$ A" }, draft_by: 7 }));
    const submit = screen.getByRole("button", { name: words.submit });
    await replaceText("$I = 0.5$ amperes");
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: words.discardChanges }));
    expect(screen.getByRole("textbox", { name: words.source })).toHaveValue("$I = 0.50$ A");
    await userEvent.click(submit);
    expect(draftAction).toHaveBeenCalledWith("solutions", 2402, "submit");
  });

  it("is read only without the permission to change it", () => {
    renderEditor(solution(), [P.solutionsView]);
    expect(screen.getByRole("textbox", { name: words.source })).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: words.save })).toBeNull();
    expect(screen.queryByRole("button", { name: words.submit })).toBeNull();
  });

  it("offers back what was typed and not saved", async () => {
    window.sessionStorage.setItem(
      "examleaf-admin:content-editor:solutions-2402",
      JSON.stringify({ body_md: "$I = 0.50$ A, kept" }),
    );
    renderEditor();
    expect(screen.getByText(words.keptTitle)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: words.keptRestore }));
    expect(screen.getByRole("textbox", { name: words.source })).toHaveValue("$I = 0.50$ A, kept");
    expect(screen.queryByText(words.keptTitle)).toBeNull();
  });
});
