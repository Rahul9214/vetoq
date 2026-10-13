import { auth } from "@clerk/nextjs/server";
import { HomeView } from "./home-view";

export default async function Home() {
  const { userId } = await auth();
  return <HomeView initialUserId={userId ?? null} />;
}
