import { PayClient } from "@/components/PayClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function PayPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <PayClient locale={normalizeLocale(locale)} />;
}
