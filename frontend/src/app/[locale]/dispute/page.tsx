import { DisputeClient } from "@/components/DisputeClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function DisputePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <DisputeClient locale={normalizeLocale(locale)} />;
}
