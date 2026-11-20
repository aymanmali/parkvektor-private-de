import { AdminClient } from "@/components/AdminClient";
import { normalizeLocale } from "@/lib/i18n";

export default async function AdminPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <AdminClient locale={normalizeLocale(locale)} />;
}
