import { IndustryGroupDetailPanel } from "@/features/industry-groups/industry-group-detail-panel";

export default async function IndustryGroupDetailPage({ params }: { params: Promise<{ groupCode: string }> }) {
  const { groupCode } = await params;
  return <IndustryGroupDetailPanel groupCode={groupCode.toUpperCase()} />;
}
