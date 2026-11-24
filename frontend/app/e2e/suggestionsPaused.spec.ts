import { buildButton, expect, lightOnly, test } from "./support";

lightOnly(() => {
  test("the not-built page says suggestions are paused when the search is rate limited", async ({
    page,
    open,
  }) => {
    // The search answers normally until Build is pressed, so the direct load reaches the unbuilt view.
    let limited = false;
    await page.route("**/api/v1/search**", (route) =>
      !limited
        ? route.fallback()
        : route.fulfill({
            status: 429,
            contentType: "application/problem+json",
            headers: { "retry-after": "30" },
            body: JSON.stringify({
              type: "about:blank",
              title: "Too Many Requests",
              status: 429,
              detail: "Too many requests.",
              code: "rate_limited",
              request_id: "spec-search-429",
              retry_after: 30,
            }),
          }),
    );
    await open("/t/Nonexistent_Title", { ready: buildButton(page) });
    limited = true;
    await buildButton(page).click();
    await expect(
      page.getByRole("heading", { level: 1, name: "No article by that title" }),
    ).toBeVisible();
    await expect(page.getByText("Suggestions paused, try again in a moment")).toBeVisible();
    await expect(page.getByText("Did you mean")).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: "Search for a topic" })).toBeVisible();
  });
});
