import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";

type Theme = "light" | "dark";

const STORAGE_KEY = "wke-theme";

// Returns null when nothing valid is stored or the browser blocks storage.
function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    return null;
  }
}

// Points every theme-color meta at the paper color of the active theme.
function syncThemeColor() {
  const paper = getComputedStyle(document.documentElement).getPropertyValue("--wke-paper").trim();
  if (!paper) {
    return;
  }
  document.head
    .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((meta) => meta.setAttribute("content", paper));
}

/**
 * Switches between the light and dark theme, starting from the stored choice or the system preference.
 * It sets `<html data-theme>`, saves the choice when storage is available, and updates the browser chrome color.
 */
export function ThemeToggle() {
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const [theme, setTheme] = useState<Theme>(
    () => readStoredTheme() ?? (prefersDark ? "dark" : "light"),
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage is blocked: the choice lasts until the page closes.
    }
    syncThemeColor();
  }, [theme]);

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="hit-44 inline-flex h-[var(--control-h)] items-center gap-x-1 px-1 text-ink-2 hover:text-ink"
    >
      {isDark ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
      {/* The label names the theme the button switches to, not the current one. */}
      <span className="text-13">{isDark ? "Light" : "Dark"}</span>
    </button>
  );
}
