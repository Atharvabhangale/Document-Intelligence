import type { HealthResponse } from "../../api/types";
import { RecentDocuments } from "./RecentDocuments";
import { UploadCard } from "./UploadCard";
import { WindchillDocumentsCard } from "./WindchillDocumentsCard";

interface HomePageProps {
  health: HealthResponse | null;
  onOpenDocument: (documentId: string) => void;
}

export function HomePage({ health, onOpenDocument }: HomePageProps) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">Select a document</h1>
        <p className="mt-1 text-muted">
          Open a Windchill document or upload a PDF to generate a structured analysis in which every
          statement cites its source page.
        </p>
      </div>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <WindchillDocumentsCard onOpen={onOpenDocument} />
        <UploadCard
          maxUploadMb={health?.limits.maxUploadMb}
          maxPages={health?.limits.maxPages}
          onUploaded={onOpenDocument}
        />
      </div>
      <RecentDocuments onOpen={onOpenDocument} />
    </div>
  );
}
