import { eachTheme, expect, test } from "./support";

eachTheme(() => {
  test("the not-built page says suggestions are paused when the search is rate limited", async ({
    page,
    open,
  }) => {
    await page.route("**/api/v1/search**", (route) =>
      route.fulfill({
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
    await open("/t/Nonexistent_Title", {
      ready: page.getByRole("heading", { level: 1, name: "No article by that title" }),
    });
    await expect(page.getByText("Suggestions paused, try again in a moment")).toBeVisible();
    await expect(page.getByText("Did you mean")).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: "Search for a topic" })).toBeVisible();
  });
});
