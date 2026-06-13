Read the file at the project root called `dev-TODO.txt` and display its full contents clearly.

If the user's message includes text after `/todo` (e.g., `/todo add implement X` or `/todo check off mulligan`), act on that instruction:
- `add <item>` — append a new unchecked item `[ ] <item>` to the list
- `done <partial text>` — find the matching item and mark it `[x]`
- `remove <partial text>` — delete the matching line

After any modification, write the updated file back and show the new list.

If no argument is given, just display the current list.
