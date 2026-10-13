import { SignIn } from "@clerk/nextjs";

import { AuthShell } from "../../../components/auth-shell";

export default function SignInPage() {
  return (
    <AuthShell mode="sign-in">
      <SignIn
        fallbackRedirectUrl="/"
        path="/sign-in"
        routing="path"
        signUpUrl="/sign-up"
      />
    </AuthShell>
  );
}
