import { useCallback, useMemo } from "react";

import type { Message } from "@/types/chat";

/**
 * Builds a tree structure from flat message list and provides
 * branch navigation utilities.
 */
export function useConversationTree(messages: Message[], activeLeafId: number | null) {
  // Build a map from message id to message
  const nodeMap = useMemo(() => {
    const map = new Map<number, Message>();
    for (const m of messages) {
      if (m.id != null) map.set(m.id, m);
    }
    return map;
  }, [messages]);

  // Build children map: parentId → sorted children
  const childrenMap = useMemo(() => {
    const map = new Map<number | null, Message[]>();
    for (const m of messages) {
      const pid = m.parentId;
      if (!map.has(pid)) map.set(pid, []);
      map.get(pid)!.push(m);
    }
    // Sort each group by siblingsOrder
    map.forEach((list) => {
      list.sort((a: Message, b: Message) => a.siblingsOrder - b.siblingsOrder);
    });
    return map;
  }, [messages]);

  // Compute the active path: from root to activeLeafId
  const activePath = useMemo(() => {
    if (messages.length === 0) return messages;
    // Determine the leaf to trace from
    let leafId: number | null = activeLeafId;
    if (leafId == null) {
      // Default: use the last message that has an id
      for (let i = messages.length - 1; i >= 0; i--) {
        const mid = messages[i].id;
        if (mid != null) { leafId = mid; break; }
      }
    }
    if (leafId == null) return messages; // no ids at all, fall back to flat list
    const path: Message[] = [];
    let current = nodeMap.get(leafId);
    while (current) {
      path.unshift(current);
      const pid = current.parentId;
      current = pid != null ? nodeMap.get(pid) : undefined;
    }
    return path.length > 0 ? path : messages;
  }, [messages, activeLeafId, nodeMap]);

  // Get siblings of a message (messages with the same parent)
  const getSiblings = useCallback((msgId: number): Message[] => {
    const msg = nodeMap.get(msgId);
    if (!msg) return [];
    const pid = msg.parentId;
    return childrenMap.get(pid) || [];
  }, [nodeMap, childrenMap]);

  // Get the index of the active sibling among its siblings
  const getActiveSiblingIndex = useCallback((msgId: number): number => {
    const siblings = getSiblings(msgId);
    return siblings.findIndex((m) => m.id === msgId);
  }, [getSiblings]);

  // Switch branch: given a message id and direction, find the next/prev sibling
  // and return the leaf of that sibling's subtree
  const switchBranch = useCallback((msgId: number, direction: "prev" | "next"): number | null => {
    const siblings = getSiblings(msgId);
    const idx = siblings.findIndex((m) => m.id === msgId);
    if (idx === -1) return null;
    const newIdx = direction === "next" ? idx + 1 : idx - 1;
    if (newIdx < 0 || newIdx >= siblings.length) return null;
    const target = siblings[newIdx];
    // Walk down to the leaf of this branch
    if (target.id == null) return null;
    let leafId = target.id;
    let children = childrenMap.get(leafId);
    while (children && children.length > 0) {
      // Pick the last child (most recent branch)
      const lastChild = children[children.length - 1];
      if (lastChild.id == null) break;
      leafId = lastChild.id;
      children = childrenMap.get(leafId);
    }
    return leafId;
  }, [getSiblings, childrenMap]);

  return { activePath, getSiblings, getActiveSiblingIndex, switchBranch };
}
