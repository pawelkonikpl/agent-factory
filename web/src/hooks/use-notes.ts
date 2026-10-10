import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createNote, fetchNotes } from "../services/notes-api";

const NOTES_QUERY_KEY = ["notes"] as const;

export function useNotes() {
  return useQuery({ queryKey: NOTES_QUERY_KEY, queryFn: fetchNotes });
}

export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createNote,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: NOTES_QUERY_KEY }),
  });
}
