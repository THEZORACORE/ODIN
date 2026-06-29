import { create } from 'zustand';
import { AssistantId } from '@/types';
import { DEFAULT_ASSISTANT_ID } from '@/data/assistants';

interface AssistantState {
  /** ID på den valgte assistent. Vil i Step 2 blive persisteret til SQLite. */
  selectedAssistantId: AssistantId;
  /** Skift aktiv assistent. */
  setAssistant: (id: AssistantId) => void;
}

export const useAssistantStore = create<AssistantState>((set) => ({
  selectedAssistantId: DEFAULT_ASSISTANT_ID,
  setAssistant: (id) => set({ selectedAssistantId: id }),
}));
