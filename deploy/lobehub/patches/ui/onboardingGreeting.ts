/**
 * Onboarding greeting message building.
 *
 * Pure helpers shared by the proactive greeting hook (`useOnboardingGreeting`).
 * Kept free of React / store imports so the ordering contract is unit-testable.
 */

export interface GreetingContextLike {
  agentId?: string;
  groupId?: string;
  threadId?: string;
  topicId?: string;
}

export interface GreetingMessageLike {
  content: string;
  createdAt: number;
}

/**
 * Build the creation payloads for the onboarding greeting bubbles so that they
 * sort as the FIRST messages of the topic.
 *
 * LobeHub orders messages by `createdAt` (ascending) on every query, so a
 * message's timestamp decides its position. The welcome fetch can resolve
 * after the user already typed a first message; a naive insert would then land
 * the greeting in the latest-reply slot at the bottom. Backdating the bubbles
 * to just before the earliest existing message keeps them pinned to the top
 * across server refreshes, streaming snapshots, and remounts.
 *
 * @param context        The conversation context the bubbles belong to.
 * @param existingMessages Current messages in the conversation (may be empty).
 * @param greetingTexts The scripted greeting bubbles, in delivery order.
 * @returns Bubble payloads ordered oldest-first, each with a `createdAt` that
 *          sorts before every existing message when the conversation started.
 */
export const buildOnboardingGreetingMessages = (
  context: GreetingContextLike,
  existingMessages: Array<{ createdAt?: Date | string | number } | undefined>,
  greetingTexts: string[],
): GreetingMessageLike[] => {
  const now = Date.now();
  let earliest = now;
  let hasExisting = false;

  for (const message of existingMessages) {
    if (!message?.createdAt) continue;
    const time = new Date(message.createdAt).getTime();
    if (Number.isFinite(time)) {
      hasExisting = true;
      if (time < earliest) earliest = time;
    }
  }

  // Anchor the greeting just before the earliest existing message when the user
  // already started the conversation; otherwise use now (empty topic).
  const anchor = hasExisting ? earliest - 1 : now;

  // Bubbles are spaced 1s apart so the first scripted bubble sorts first.
  // The first bubble is the oldest; the last bubble sits at the anchor.
  return greetingTexts.map((content, index) => ({
    content,
    createdAt: anchor - (greetingTexts.length - 1 - index) * 1000,
  }));
};