import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithRouter } from "../../test/renderWithRouter";
import type { Budget } from "../budget";
import { useOpenDossier } from "./useOpenDossier";

function Opener({ budget }: { budget: Budget }) {
  const open = useOpenDossier(budget);
  return <button onClick={() => open("Mary_Magdalene")}>open</button>;
}

describe("useOpenDossier", () => {
  it("opens the dossier route of the slug at the given budget", async () => {
    const { router } = renderWithRouter(<Opener budget={2000} />, {
      extraRoutes: ["/t/$slug"],
    });
    fireEvent.click(await screen.findByRole("button", { name: "open" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/t/Mary_Magdalene"));
    expect(router.state.location.search).toEqual({ budget: 2000 });
  });
});
