import { useRef, useState, useEffect } from "react";
import { sendChatMessage } from "../lib/api";
import type { ChatMessage } from "../lib/types";
import { WhaleSharkLogo } from "./WhaleSharkLogo";

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "Hi — I can explain how the dashboard works, what the filters do, or what consensus score means. What do you need?" },
  ]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  const send = async () => {
    const text = draft.trim();
    if (!text || loading) return;
    const history = messages;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setDraft("");
    setLoading(true);
    try {
      const { reply } = await sendChatMessage(text, history);
      setMessages((m) => [...m, { role: "assistant", content: reply }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Something went wrong — try again in a moment." }]);
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Open chat assistant"
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-2xl transition-transform hover:scale-105"
      >
        <WhaleSharkLogo size={28} className="text-white" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex h-[520px] w-[360px] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-xl border border-[var(--border-hairline)] bg-[var(--bg-surface)] shadow-2xl">
      <div className="flex items-center justify-between border-b border-[var(--border-hairline)] px-4 py-3">
        <div className="flex items-center gap-2">
          <WhaleSharkLogo size={20} className="text-[var(--accent)]" />
          <span className="text-sm font-medium">Whale Sharks Assistant</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
          ✕
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-[var(--accent)] text-white"
                  : "bg-[var(--bg-surface-raised)] text-[var(--text-primary)]"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && <div className="text-sm text-[var(--text-muted)]">Thinking…</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex gap-2 border-t border-[var(--border-hairline)] p-3"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded-md border border-[var(--border-hairline)] bg-[var(--bg-page)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !draft.trim()}
          className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
