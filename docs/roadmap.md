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
- [x] **Interactive comb cells** -- Give workers the possibility to add cells that are more customized and interactive.
- [ ] **Improve agent output** -- Currently all LLM messages are concatenated without spaces and without tool calls. I think this could be improved to make agent responses more intuitive. For example, each LLM message could be a different telegram message, and the tools called could be also different messages, even if the outputs aren't added to keep the chat clean.

## Backlog

- [ ] **Better agent session management UI** -- Currently the only way to manage the agent session is with the `/reset` command, but there's no way to see past sessions or return to them.
- [ ] **Chat UI alternative to Telegram** -- Creating our own chat app (either web or iOS) would allow us to improve the UX of hive for our use cases, like agent session management.
- [ ] **Worker creator wizard/assistant** -- Currently we have a create-worker skill, but I think a dedicated wizard/assistant would be easier to use and more helpful.
- [ ] **Add Plan Mode** -- Maybe each time an agent wants to make changes, they should enter plan mode first? Then a plan is suggested, in a way that is visually appealing, and the agent works on it.
