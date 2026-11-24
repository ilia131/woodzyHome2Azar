import { notFound } from "next/navigation";
import { ConnectionRequired, Workspace } from "@/components/workspace";
import { adminNav, adminSection } from "@/features/admin";
import { demo } from "@/lib/catalog";
import type { Query } from "@/lib/types";

type Props = { params: Promise<{section: string}>; searchParams: Promise<Query> };
export async function generateMetadata({ params }: Props) {
  const { section } = await params;
  return { title: adminNav.find(([slug]) => slug === section)?.[1], robots: { index: false, follow: false } };
}
export default async function Page({ params, searchParams }: Props) {
  const [{ section }, query] = await Promise.all([params, searchParams]);
  const screen = adminNav.find(([slug]) => slug === section);
  if (!screen) notFound();
  const showConnection = demo;
  return <Workspace root="/admin" section={section} title={screen[1]} nav={adminNav} query={query}>{showConnection ? <ConnectionRequired/> : await adminSection(section, query)}</Workspace>;
}
