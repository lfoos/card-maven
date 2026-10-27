import type { AuthContextProps } from "react-oidc-context";
import { vi } from "vitest";

/** A minimal useAuth() result; override fields per test. */
export function mockAuth(overrides: Partial<AuthContextProps> = {}): AuthContextProps {
  return {
    isLoading: false,
    isAuthenticated: false,
    activeNavigator: undefined,
    error: undefined,
    user: null,
    signinRedirect: vi.fn().mockResolvedValue(undefined),
    signoutRedirect: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as AuthContextProps;
}
