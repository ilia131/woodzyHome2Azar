import { notFound } from "next/navigation";
import { ConnectionRequired, Workspace } from "@/components/workspace";
import { accountNav, customerSection } from "@/features/customer";
import { demo } from "@/lib/catalog";
import type { Query } from "@/lib/types";

type Props = { params: Promise<{section: string}>; searchParams: Promise<Query> };
export async function generateMetadata({ params }: Props) {
  const { section } = await params;
  return { title: accountNav.find(([slug]) => slug === section)?.[1], robots: { index: false, follow: false } };
}
export default async function Page({ params, searchParams }: Props) {
  const [{ section }, query] = await Promise.all([params, searchParams]);
  const screen = accountNav.find(([slug]) => slug === section);
  if (!screen) notFound();
  const showConnection = demo && section !== "auth" && section !== "recovery";
  return <Workspace root="/account" section={section} title={screen[1]} nav={accountNav} query={query}>{showConnection ? <ConnectionRequired/> : await customerSection(section, query)}</Workspace>;
}
