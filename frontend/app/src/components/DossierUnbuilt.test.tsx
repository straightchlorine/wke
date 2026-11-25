import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithRouter } from "../test/renderWithRouter";
import { DossierUnbuilt } from "./DossierUnbuilt";

describe("DossierUnbuilt", () => {
  it("shows the title as the heading and says the topic is not built yet", async () => {
    renderWithRouter(<DossierUnbuilt title="Kamchatka Peninsula" onBuild={vi.fn()} />);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Kamchatka Peninsula" }),
    ).toBeTruthy();
    expect(
      screen.getByText("This topic is not built yet. Build it to read its dossier."),
    ).toBeTruthy();
  });

  it("calls onBuild from the Build dossier button", async () => {
    const onBuild = vi.fn();
    renderWithRouter(<DossierUnbuilt title="Kamchatka Peninsula" onBuild={onBuild} />);
    fireEvent.click(await screen.findByRole("button", { name: "Build dossier" }));
    expect(onBuild).toHaveBeenCalledTimes(1);
  });
});
