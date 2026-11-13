import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useScrollRestoration } from "./useScrollRestoration";

interface Props {
  pathname: string;
  hash: string;
  settled: boolean;
}

function setEntry(key: string, path: string) {
  window.history.replaceState({ __TSR_key: key }, "", path);
}

function setScrollY(value: number) {
  Object.defineProperty(window, "scrollY", { value, configurable: true });
}

function addTarget(id: string): HTMLElement {
  const element = document.createElement("div");
  element.id = id;
  document.body.append(element);
  return element;
}

function mount(initial: Props) {
  return renderHook(
    (props: Props) => useScrollRestoration(props.pathname, props.hash, props.settled),
    {
      initialProps: initial,
    },
  );
}

describe("useScrollRestoration", () => {
  const scrollIntoView = vi.fn();
  const scrollTo = vi.fn();

  beforeEach(() => {
    scrollIntoView.mockReset();
    scrollTo.mockReset();
    Element.prototype.scrollIntoView = scrollIntoView;
    vi.stubGlobal("scrollTo", scrollTo);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 0;
    });
    setScrollY(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.replaceChildren();
    Reflect.deleteProperty(document, "fonts");
  });

  it("scrolls to the hash target of a direct load once the router has settled", () => {
    const target = addTarget("s2");
    setEntry("load-1", "/t/a#s2");
    const { rerender } = mount({ pathname: "/t/a", hash: "#s2", settled: false });
    expect(scrollIntoView).not.toHaveBeenCalled();
    rerender({ pathname: "/t/a", hash: "#s2", settled: true });
    expect(scrollIntoView).toHaveBeenCalledOnce();
    expect(scrollIntoView.mock.contexts[0]).toBe(target);
  });

  it("waits for a hash target that mounts later", async () => {
    setEntry("late-1", "/t/a#late");
    mount({ pathname: "/t/a", hash: "#late", settled: true });
    expect(scrollIntoView).not.toHaveBeenCalled();
    const target = addTarget("late");
    await vi.waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    expect(scrollIntoView.mock.contexts[0]).toBe(target);
  });

  it("scrolls on a same-page hash change but not when only the search changes", () => {
    addTarget("s1");
    addTarget("s3");
    setEntry("hash-1", "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    rerender({ pathname: "/t/a", hash: "#s3", settled: false });
    rerender({ pathname: "/t/a", hash: "#s3", settled: true });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    rerender({ pathname: "/t/a", hash: "#s3", settled: false });
    rerender({ pathname: "/t/a", hash: "#s3", settled: true });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("leaves a plain route change to the router", () => {
    setEntry("plain-1", "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    setEntry("plain-2", "/t/b");
    rerender({ pathname: "/t/b", hash: "", settled: true });
    expect(scrollTo).not.toHaveBeenCalled();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it.each([
    ["a click", () => document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }))],
    [
      "a key press",
      () => document.body.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true })),
    ],
    ["scrolling alone", () => window.dispatchEvent(new Event("scroll"))],
  ])("restores the position recorded by %s when Back returns to an entry", (name, record) => {
    const key = `back-${name}`;
    setEntry(key, "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    setScrollY(640);
    record();

    setEntry(`${key}-next`, "/t/b");
    setScrollY(0);
    rerender({ pathname: "/t/b", hash: "", settled: true });

    setEntry(key, "/t/a");
    window.dispatchEvent(new PopStateEvent("popstate"));
    rerender({ pathname: "/t/a", hash: "", settled: true });
    expect(scrollTo).toHaveBeenCalledWith(0, 640);
  });

  it("scrolls to the hash after Back to an entry with no recorded position", () => {
    addTarget("s4");
    setEntry("nosave-1", "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    setEntry("nosave-2", "/t/b#s4");
    rerender({ pathname: "/t/b", hash: "#s4", settled: true });
    scrollIntoView.mockClear();

    setEntry("nosave-3", "/t/c#s4");
    window.dispatchEvent(new PopStateEvent("popstate"));
    rerender({ pathname: "/t/c", hash: "#s4", settled: true });
    expect(scrollTo).not.toHaveBeenCalled();
    expect(scrollIntoView).toHaveBeenCalledOnce();
  });

  it("treats a navigation after Back as a new one", () => {
    addTarget("s5");
    setEntry("after-1", "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    setEntry("after-2", "/t/b");
    rerender({ pathname: "/t/b", hash: "", settled: true });
    setEntry("after-1", "/t/a");
    window.dispatchEvent(new PopStateEvent("popstate"));
    rerender({ pathname: "/t/a", hash: "", settled: true });

    setEntry("after-3", "/t/a#s5");
    setScrollY(77);
    window.dispatchEvent(new Event("scroll"));
    rerender({ pathname: "/t/a", hash: "#s5", settled: true });
    expect(scrollIntoView).toHaveBeenCalledOnce();
    expect(scrollTo).not.toHaveBeenCalledWith(0, 77);
  });

  it("scrolls to the target again once fonts have loaded", async () => {
    Object.defineProperty(document, "fonts", {
      value: { ready: Promise.resolve() },
      configurable: true,
    });
    addTarget("s6");
    setEntry("fonts-1", "/t/a#s6");
    mount({ pathname: "/t/a", hash: "#s6", settled: true });
    await vi.waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2));
  });

  it("keeps two entries of the same path apart", () => {
    addTarget("s9");
    setEntry("same-1", "/t/a");
    const { rerender } = mount({ pathname: "/t/a", hash: "", settled: true });
    setScrollY(300);
    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    setEntry("same-2", "/t/a#s9");
    setScrollY(1200);
    rerender({ pathname: "/t/a", hash: "#s9", settled: true });
    window.dispatchEvent(new Event("scroll"));

    setEntry("same-1", "/t/a");
    window.dispatchEvent(new PopStateEvent("popstate"));
    rerender({ pathname: "/t/a", hash: "", settled: true });
    expect(scrollTo).toHaveBeenCalledWith(0, 300);
  });
});
