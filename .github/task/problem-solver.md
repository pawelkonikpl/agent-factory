# Uniwersalny solver problemów technicznych (`/solve`)

## Cel

Obok fabryki (`/factory`) dodać system agentów do rozwiązywania problemów
technicznych i problemów w kodzie: błędów, niestabilnych testów, problemów z
wydajnością oraz pytań technicznych, na które trzeba odpowiedzieć z dowodami.
Projekt wynika z dokumentu „Uniwersalny system rozwiązywania problemów na
agentach LLM” i realizuje jego etap 1 (MVP): pętlę z zewnętrzną weryfikacją,
domyślnie jednego wykonawcę i zestaw testowy z ukrytymi oceniaczami.

## Kontekst

- Fabryka to skill-orkiestrator (`.claude/skills/factory/SKILL.md`) i agenci w
  `.claude/agents/`. Model każdego agenta jest ustawiony we frontmatterze.
  Każdy agent pisze jeden plik, którego pierwsza linia to status lub werdykt.
  Każde zadanie dostaje osobny git worktree, a stan zadania trzyma `job.json`.
- `/solve` używa tych samych konwencji, żeby oba systemy czytało się i
  utrzymywało tak samo.

## Zakres

1. Skill `.claude/skills/solve/SKILL.md` (orkiestrator) z komendami:
   - `/solve <problem>`,
   - `/solve eval [case-id] [--baseline]`,
   - `/solve apply <job-id> [c<k>]`,
   - `/solve clean <job-id>`.
2. Sześciu agentów w `.claude/agents/solve-*.md`. W nawiasie model i plik, który
   agent pisze:
   - `analyst` (opus, `brief.md`),
   - `investigator` (sonnet, `findings-q<n>.md`),
   - `solver` (opus, `candidate-c<k>.md` + commity),
   - `verifier` (sonnet, `verify-c<k>.md`),
   - `critic` (opus, `critique-c<k>.md`),
   - `synthesizer` (opus, `answer.md` + `lessons.md`).
3. Zestaw testowy w `solve/evals/`:
   - 5 przypadków w `cases/`,
   - ukryte oceniacze i wzorcowe łatki w `hidden/`,
   - `selftest.sh`, który sprawdza same oceniacze.
4. `make solve-selftest`, wpis `solve/jobs/` w `.gitignore`, sekcja w
   README.md, wpis w AGENTS.md.

## Kryteria akceptacji

1. `.claude/skills/solve/SKILL.md` ma frontmatter z polami `name: solve`,
   `description` i `argument-hint` oraz opisuje wszystkie cztery komendy.
2. Istnieje sześć plików `.claude/agents/solve-*.md`. Każdy ma `name`,
   `description`, `tools`, `model` i `maxTurns`. Żaden nie ma narzędzia `Agent`.
   Sprawdzenie: `grep -L "^model:" .claude/agents/solve-*.md` nic nie wypisuje,
   a `grep -l "Agent" .claude/agents/solve-*.md | xargs grep "^tools:.*Agent"`
   nic nie znajduje.
3. Pierwsze linie plików w SKILL.md zgadzają się z tymi w plikach agentów:
   - `STATUS: READY|NEEDS-INPUT` (brief),
   - `STATUS: DONE|PARTIAL` (findings),
   - `STATUS: READY|BLOCKED` (candidate),
   - `VERDICT: PASS|FAIL` (verify),
   - `VERDICT: STANDS|REFUTED` (critique),
   - `STATUS: SOLVED c<k>|UNSOLVED` (answer).
4. `make solve-selftest` (albo `bash solve/evals/selftest.sh`) wypisuje `ok`
   dla każdego z 5 przypadków i kończy się kodem 0. Każdy oceniacz nie przechodzi
   na kodzie z repo i przechodzi po nałożeniu wzorcowej łatki.
5. W każdym przypadku widoczne testy (`python3 -m unittest` w katalogu
   przypadku) przechodzą albo są niestabilne, tak jak opisuje `problem.md`.
   Błąd widać dopiero po reprodukcji.
6. `.gitignore` zawiera `solve/jobs/`.
7. Pliki fabryki (`.claude/skills/factory/`, dotychczasowi agenci, `factory/`)
   są niezmienione: `git diff main -- .claude/skills/factory .claude/agents/builder.md factory/`
   jest pusty.

## Poza zakresem

- Dashboard dla `/solve`.
- Pętla ewolucyjna i solwery formalne (etap 4 dokumentu).
- Przypadki oceniane rubryką, bez oceniacza-skryptu.
- Komunikacja A2A z agentami zewnętrznymi.

## Decyzje i założenia

- Domena startowa to problemy techniczne i kod, bo tu najłatwiej o twardą
  weryfikację testami.
- Interfejs to skill + agenci. Modele są ustawione we frontmatterze plików
  agentów: wykonawca i weryfikator na sonnet, reszta na opus.
- Kod, skille i ewaluacje są po angielsku (reguła repo), a ten plan po polsku.
- Ukrycie oceniaczy działa na zasadzie zaufania: agenci mają zakaz czytania
  `solve/evals/hidden/`. To znane ograniczenie.

## Następne kroki

1. Uzupełnić zestaw do ok. 20 realnych problemów z oczekiwanym wynikiem.
2. Uruchomić `/solve eval --baseline` i `/solve eval`. Bramka etapu 1: pełna
   pętla wygrywa z wersją bazową.
