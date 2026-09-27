import { useEffect, useState, useSyncExternalStore } from "react";
import type { AgentClient, ConnectionState } from "../agent/client.ts";
import type { Conversation } from "./conversation.ts";
import { ConversationStore } from "./store.ts";

/** The typed conversation with the agent, and a way to send to it. */
export function useConversation(
  agent: AgentClient,
  connection: ConnectionState,
): { conversation: Conversation; send: (text: string) => boolean } {
  const [store] = useState(() => new ConversationStore());
  useEffect(() => agent.onTurnFrame(store.apply), [agent, store]);
  useEffect(() => () => store.dispose(), [store]);
  useEffect(() => {
    if (connection !== "open") store.disconnected();
  }, [connection, store]);
  const conversation = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getSnapshot,
  );
  const send = (text: string): boolean => {
    if (!agent.say(text)) return false;
    store.said(text);
    return true;
  };
  return { conversation, send };
}
