# Shared chatbot/wiki session lifetime and revocation

> **For agentic workers:** use subagent-driven-development for the independent frontend and chatbot pieces; root owns wiki backend integration and final validation.

**Goal:** A wiki session created through chatbot SSO cannot outlive or remain authorized after its source chatbot session ends. Open wiki tabs react to expiration, revocation and logout.

**Architecture:** Chatbot issues an encrypted opaque parent-session proof with the existing short-lived signed login ticket. Wiki caps its own JWT at the signed parent deadline and embeds only the opaque proof, never a plaintext chatbot bearer. Each authenticated wiki API request validates the parent through a fixed backend-to-backend chatbot endpoint. Invalid/expired/revoked sessions return 401; verifier outages deny access with 503 rather than falsely asserting invalid credentials. Direct OIDC fallback is likewise capped and checked against the provider. Version the new wiki tokens so pre-fix SSO tokens cannot bypass binding; existing sessions must authenticate once after deployment. Local wiki emergency password login remains a separate, explicitly tagged policy.

**Tech stack:** Existing FastAPI, PyJWT, cryptography, httpx, React/TypeScript, pytest and Node regression harnesses. No new service or dependency.

## Tasks

- [x] Write failing chatbot regression tests: proof confidentiality/tamper/expiry, source-session deletion/account disable, ticket deadline and logout revocation; implement proof endpoint and ticket claims.
- [x] Write failing wiki backend tests: parent deadline cap, expired/legacy/malformed session rejection, per-request parent verification, inactive/identity mismatch, network failure; implement token version, SSO binding and verifier service.
- [x] Cover the direct OIDC login fallback with provider expiry and active-token validation.
- [x] Frontend tests first: token expiry scheduling, same-tab and cross-tab logout, authenticated 401, stale-response race, normal 403/network errors; implement event handling, expiry timer and periodic/focus checks in AuthProvider and API wrapper. Reuse existing portal login routing.
- [x] Document and configure the backend-only chatbot URL without disclosing or changing existing secrets.
- [x] Run targeted backend regressions, full frontend TypeScript/lint and executable session lifecycle harness. Perform isolated integration requests without ending the user's real login.
- [x] Review source binding and revocation paths, deploy checked local services when appropriate and report any rollout limitation. Never claim a production build from a dev run.

## Security and operational constraints

Parent proof uses a purpose-specific authenticated encryption key derived from the existing SSO shared secret. Introspection accepts it in POST body only, does not return the parent bearer, and validates the original chatbot JWT, account status and server-side SSO row. No cache in wiki grants access after a source revocation; frontend polling is only for idle-screen cleanup, not authorization. Keep document/agent/skill changes in both working trees intact. Do not log tokens or complete environment/configuration objects.

## Validation and rollout (2026-10-20)

53 wiki auth/SSO/MCP regressions, 37 chatbot session regressions and 20 executable frontend lifecycle checks passed. Full frontend TypeScript and targeted ESLint passed. Review caught and repaired provider outages incorrectly becoming inactive sessions; both sides now deny access with 503 without clearing browser authentication on verifier outage. Chatbot SSO tickets require a revocable server-side sid; no-sid password/subagent JWTs cannot create wiki SSO. Wiki local emergency login and native Keycloak proxy/MCP authorization retain their separate policies.

Local wiki API was recreated with CHATBOT_INTERNAL_URL=http://cahy_chatbot:8080. A backend-only image layer containing the two changed chatbot files was built on the existing local chatbot image, then its container was recreated. The wiki frontend runs npm run dev on 127.0.0.1:3219 with API rewrites to 127.0.0.1:5155; its Docker frontend is stopped. This is not a frontend production build. Live isolated HTTP checks confirmed shared proof decryption, inactive-parent and legacy-session rejection, temporary-file rejection and deadline caps, without modifying an actual account/session. Existing unbound wiki sessions require one fresh SSO login.
