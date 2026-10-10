import { useMutation, useQuery } from "@tanstack/react-query";

import { fetchSession, logout } from "../services/session-api";

export const SESSION_QUERY_KEY = ["session"] as const;

export function useSession() {
  return useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: fetchSession, staleTime: 60_000 });
}

export function useLogout() {
  return useMutation({ mutationFn: logout });
}
