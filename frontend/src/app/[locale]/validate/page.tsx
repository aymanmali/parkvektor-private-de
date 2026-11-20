import { ValidateClient } from "@/components/ValidateClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function ValidatePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ValidateClient locale={normalizeLocale(locale)} />;
}
