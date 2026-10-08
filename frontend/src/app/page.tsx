import { connection } from "next/server";
import { HomeDashboard } from "@/features/home/home-dashboard";
import { BetaHomeDashboard } from "@/features/home/beta-home-dashboard";
import { isBetaMode } from "@/lib/beta/policy";
export default async function Page() {
  await connection();
  return isBetaMode() ? <BetaHomeDashboard /> : <HomeDashboard />;
}
