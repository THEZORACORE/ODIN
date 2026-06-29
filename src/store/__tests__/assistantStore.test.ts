import { useAssistantStore } from '../assistantStore';

// Zustand-stores kan testes direkte uden at rendere React-komponenter

describe('assistantStore', () => {
  beforeEach(() => {
    // Nulstil til kendt tilstand mellem tests
    useAssistantStore.setState({ selectedAssistantId: 'CONNOR' });
  });

  it('starter med CONNOR som standard', () => {
    expect(useAssistantStore.getState().selectedAssistantId).toBe('CONNOR');
  });

  it('setAssistant skifter til LUMINA', () => {
    useAssistantStore.getState().setAssistant('LUMINA');
    expect(useAssistantStore.getState().selectedAssistantId).toBe('LUMINA');
  });

  it('setAssistant kan skifte tilbage til CONNOR', () => {
    useAssistantStore.getState().setAssistant('LUMINA');
    useAssistantStore.getState().setAssistant('CONNOR');
    expect(useAssistantStore.getState().selectedAssistantId).toBe('CONNOR');
  });
});
