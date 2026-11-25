import { afterEach, describe, expect, it } from "vitest";
import { act, screen } from "@testing-library/react";
import { rootNavState } from "../../routes/__root";
import { renderWithRouter } from "../../test/renderWithRouter";
import { useBuildOnArrival } from "./useBuildOnArrival";

function Probe({ slug }: { slug: string }) {
  return <p>{useBuildOnArrival(slug) ? "builds" : "waits"}</p>;
}

afterEach(() => {
  rootNavState.isInitialLoad = true;
});

describe("useBuildOnArrival", () => {
  it("is false on the page the app was opened on", async () => {
    rootNavState.isInitialLoad = true;
    renderWithRouter(<Probe slug="Opened_Directly" />);
    expect(await screen.findByText("waits")).toBeTruthy();
  });

  it("is true for a page reached by a navigation inside the app", async () => {
    rootNavState.isInitialLoad = false;
    renderWithRouter(<Probe slug="Reached_By_Link" />);
    expect(await screen.findByText("builds")).toBeTruthy();
  });

  it("stays false when the reader leaves the first page and comes back with Back", async () => {
    rootNavState.isInitialLoad = true;
    const { router } = renderWithRouter(<Probe slug="Back_To_Direct" />, {
      extraRoutes: ["/elsewhere"],
    });
    await screen.findByText("waits");
    // By the time the reader clicks a link, the app's first render is over.
    rootNavState.isInitialLoad = false;
    act(() => router.history.push("/elsewhere"));
    expect(screen.queryByText("waits")).toBeNull();
    act(() => router.history.back());
    expect(await screen.findByText("waits")).toBeTruthy();
  });

  it("is true for another page opened after the first one", async () => {
    rootNavState.isInitialLoad = true;
    const first = renderWithRouter(<Probe slug="First_Page" />);
    await screen.findByText("waits");
    first.unmount();
    rootNavState.isInitialLoad = false;
    renderWithRouter(<Probe slug="Second_Page" />);
    expect(await screen.findByText("builds")).toBeTruthy();
  });
});
