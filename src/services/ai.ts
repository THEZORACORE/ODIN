import { AssistantId } from '@/types';

/**
 * Interface for én besked i en samtale.
 * Spejler Anthropic API's message-format, så migrationen i Step 8 er minimal.
 */
export interface AIMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AIResponse {
  message: string;
  timestamp: Date;
}

/**
 * Send en besked til assistenten og modtag et svar.
 *
 * MOCK — returnerer statiske svar baseret på assistentens id.
 * Erstattes i Step 8 med rigtige Anthropic API-kald via dette samme interface.
 */
export async function sendMessage(
  assistantId: AssistantId,
  _userMessage: string,
  _history: AIMessage[] = [],
): Promise<AIResponse> {
  // Simuleret netværksforsinkelse — fjernes når rigtig API tilkobles
  await new Promise((resolve) => setTimeout(resolve, 800));

  const mockResponses: Record<AssistantId, string> = {
    CONNOR: 'Det lyder fornuftigt. Lad os tage det ét skridt ad gangen.',
    LUMINA: 'Tak for at dele det! Jeg er her — hvad har du brug for nu?',
  };

  return {
    message: mockResponses[assistantId],
    timestamp: new Date(),
  };
}
