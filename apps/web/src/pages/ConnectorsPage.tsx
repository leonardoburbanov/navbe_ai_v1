import { DestinationsPanel } from "../components/connectors/DestinationsPanel";
import { SourcesPanel } from "../components/connectors/SourcesPanel";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";

type Tab = "sources" | "destinations";

type Props = {
  tab: Tab;
  focusType?: string | null;
  onTabChange: (tab: Tab) => void;
  onOpenReports?: (templateId: string) => void;
};

/** Connectors hub: Sources | Destinations (email is a destination type). */
export function ConnectorsPage({
  tab,
  focusType,
  onTabChange,
  onOpenReports,
}: Props) {
  return (
    <section>
      <h2 className="mt-0 text-xl font-semibold">Connectors</h2>
      <p className="mt-0 text-sm text-muted-foreground">
        Sources pull data; destinations store or deliver it (including email).
      </p>
      <Tabs
        value={tab}
        onValueChange={(v) => onTabChange(v as Tab)}
        className="mt-4"
      >
        <TabsList>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="destinations">Destinations</TabsTrigger>
        </TabsList>
        <TabsContent value="sources" className="mt-4">
          <SourcesPanel />
        </TabsContent>
        <TabsContent value="destinations" className="mt-4">
          <DestinationsPanel
            focusType={focusType}
            onOpenReports={onOpenReports}
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}
