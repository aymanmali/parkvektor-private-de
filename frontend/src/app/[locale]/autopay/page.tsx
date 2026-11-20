import { AutoPayClient } from "@/components/AutoPayClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function AutoPayPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <AutoPayClient locale={normalizeLocale(locale)} />;
}
