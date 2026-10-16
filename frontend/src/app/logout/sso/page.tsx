"use client";

import { useEffect } from "react";
import { clearToken } from "@/lib/api";

/**
 * Keycloak front-channel logout target. When the user signs out of the chatbot
 * (or any client in the realm), Keycloak loads this page in an iframe and the
 * wiki session stored in this browser is dropped too.
 */
export default function SsoFrontChannelLogoutPage() {
  useEffect(() => {
    if (localStorage.getItem("arkon_sso") === "1") {
      clearToken();
      localStorage.removeItem("arkon_sso");
    }
  }, []);

  return null;
}
