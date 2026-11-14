function isHidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

/**
 * Calls `poll` at once, then again after each delay it returns in milliseconds, until it returns
 * null or the returned function is called. A hidden tab arms no timer, and a poll runs as soon as
 * the tab is shown again. `poll` receives a signal that aborts on stop, must not reject, and should
 * ignore its result once aborted.
 */
export function startVisiblePoll(
  poll: (signal: AbortSignal) => Promise<number | null>,
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | null = null;
  // True while no timer is armed only because the tab is hidden.
  let waitingForVisible = false;

  function arm(delayMs: number) {
    if (isHidden()) {
      waitingForVisible = true;
      return;
    }
    timer = setTimeout(() => {
      timer = null;
      void run();
    }, delayMs);
  }

  async function run() {
    const nextDelayMs = await poll(controller.signal);
    if (nextDelayMs !== null && !controller.signal.aborted) {
      arm(nextDelayMs);
    }
  }

  function handleVisibilityChange() {
    if (isHidden()) {
      if (timer) {
        clearTimeout(timer);
        timer = null;
        waitingForVisible = true;
      }
    } else if (waitingForVisible) {
      waitingForVisible = false;
      void run();
    }
  }

  document.addEventListener("visibilitychange", handleVisibilityChange);
  void run();

  return () => {
    controller.abort();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
}
