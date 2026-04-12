# Hive Roadmap

Tracks features, bugs, and backlog items. Format:

```
- [ ] **Title** — brief summary
  - Extra context, motivation, repro steps, affected files, etc.
- [x] **Title** — completed item
```

---

## Bugs

- [ ] **Scheduled tasks notifications**
  - Currently scheduled tasks notify inconsistently.
    - "agent_prompt" tasks send a message on the telegram chat, and they seem to be sent to the same session the agent was currently using.
    - "run" tasks are run silently, without any notifications being sent 

## Features

- [ ] **Logging improvements**
  - Worker logs are saturated with `getUpdates` calls, and they don't show much information about other calls.
  - Meanwhile agent logs are insufficient, they don't show much of the agent's chain of thoughts or tool calls and tools results.
  - I think we should keep records of chats with the agent better.
- [ ] **CLAUDE.md personalization**
- [ ] **Better table outputs for workers** -- Currently when workers output tables, either through commands or printed by the agent, these often get broken by Telegram's message width, and are pretty ilegible. We should find a better way to handle this.
- [ ] **Interactive comb cells** -- Give workers the possibility to add cells that are more customized and interactive.

## Backlog

- [ ] **Better agent session management UI** -- Currently the only way to manage the agent session is with the `/reset` command, but there's no way to see past sessions or return to them.
- [ ] **Chat UI alternative to Telegram** -- Creating our own chat app (either web or iOS) would allow us to improve the UX of hive for our use cases, like agent session management.
