import { KioskClient } from "@/components/KioskClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function KioskPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <KioskClient locale={normalizeLocale(locale)} />;
}
