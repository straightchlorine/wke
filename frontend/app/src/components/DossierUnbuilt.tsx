import { Button } from "./Button";
import { DossierHead } from "./DossierHead";

export interface DossierUnbuiltProps {
  title: string;
  /** Called when the reader asks for the build. */
  onBuild: () => void;
}

/** The page for an unbuilt title opened directly, with a button that builds it. */
export function DossierUnbuilt({ title, onBuild }: DossierUnbuiltProps) {
  return (
    <div className="min-h-svh w-full py-8">
      <DossierHead
        title={title}
        lede="This topic is not built yet. Build it to read its dossier."
      />
      <Button variant="primary" className="mt-6" onClick={onBuild}>
        Build dossier
      </Button>
    </div>
  );
}
