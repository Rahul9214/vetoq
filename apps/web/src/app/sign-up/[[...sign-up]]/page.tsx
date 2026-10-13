import { SignUp } from "@clerk/nextjs";

import { AuthShell } from "../../../components/auth-shell";

export default function SignUpPage() {
  return (
    <AuthShell mode="sign-up">
      <SignUp
        fallbackRedirectUrl="/"
        path="/sign-up"
        routing="path"
        signInUrl="/sign-in"
      />
    </AuthShell>
  );
}
