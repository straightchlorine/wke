import { fetchDossierMarkdownText, nestDossier, type DossierView } from "../../api/dossier";
import { budgetAlias, type Budget } from "../budget";
import { formatNumber } from "../format";
import { seedPin } from "../sourceRecord";

function triggerDownload(text: string, filename: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export interface DossierExports {
  /** Fetches the dossier as Markdown at the page's budget, or returns null when the request failed. */
  fetchAsContext: () => Promise<string | null>;
  /** The message shown after the Markdown is copied. */
  copyMessage: string;
  /** Downloads the Markdown, or reports through `onToast` that it could not be fetched. */
  downloadMarkdown: () => Promise<void>;
  /** Downloads the dossier as the API's own JSON. */
  downloadJson: () => void;
}

/**
 * Copy and download actions for a dossier: copy it as context, or download it as Markdown or JSON.
 * The JSON takes the full dossier, including the sections the page leaves out for having no prose.
 */
export function useDossierExports(
  dossier: DossierView | undefined,
  fullDossier: DossierView | undefined,
  slug: string,
  budget: Budget,
  onToast: (message: string) => void,
): DossierExports {
  const pageId = dossier?.topic.page_id;
  const fetchAsContext = async () =>
    pageId == null ? null : fetchDossierMarkdownText(pageId, budget);

  const copyMessage = dossier
    ? `Copied as text/markdown, ${formatNumber(dossier.budget.used_est_tokens)} dossier tokens, revision ${seedPin(dossier)?.rev_id ?? ""}`
    : "Copied as context";

  async function downloadMarkdown() {
    const text = await fetchAsContext();
    if (text == null) {
      onToast("Download failed");
      return;
    }
    triggerDownload(text, `${slug}-${budgetAlias(budget)}.md`, "text/markdown");
  }

  function downloadJson() {
    if (!fullDossier) return;
    triggerDownload(
      JSON.stringify(nestDossier(fullDossier), null, 2),
      `${slug}-${budgetAlias(budget)}.json`,
      "application/json",
    );
  }

  return { fetchAsContext, copyMessage, downloadMarkdown, downloadJson };
}
