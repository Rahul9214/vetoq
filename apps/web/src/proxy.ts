import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedPage = createRouteMatcher(["/runs(.*)", "/tickets(.*)"]);

// The BFF must stay in the matcher so Clerk can attach session state for auth(),
// but it is never protect()ed here: protect() answers non-document requests with
// an HTML 404, while the BFF itself returns the JSON 401 contract.
export default clerkMiddleware(async (auth, request) => {
  if (isProtectedPage(request)) await auth.protect();
});

export const config = {
  matcher: [
    "/",
    "/sign-in/:path*",
    "/sign-up/:path*",
    "/runs/:path*",
    "/tickets/:path*",
    "/api/:path*",
  ],
};
