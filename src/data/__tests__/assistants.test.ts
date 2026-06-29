import { ASSISTANTS, DEFAULT_ASSISTANT_ID } from '../assistants';

describe('ASSISTANTS', () => {
  it('indeholder CONNOR og LUMINA', () => {
    expect(ASSISTANTS.CONNOR).toBeDefined();
    expect(ASSISTANTS.LUMINA).toBeDefined();
  });

  it('alle påkrævede felter er udfyldt for hver assistent', () => {
    for (const assistant of Object.values(ASSISTANTS)) {
      expect(assistant.id).toBeTruthy();
      expect(assistant.name).toBeTruthy();
      expect(assistant.personalityDescription).toBeTruthy();
      expect(assistant.toneOfVoice).toBeTruthy();
      // Hex-farver skal matche #RRGGBB formatet
      expect(assistant.accentColor).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(assistant.accentColorDark).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it('DEFAULT_ASSISTANT_ID peger på en eksisterende assistent', () => {
    expect(ASSISTANTS[DEFAULT_ASSISTANT_ID]).toBeDefined();
  });

  it('CONNOR er mand og LUMINA er kvinde', () => {
    expect(ASSISTANTS.CONNOR.gender).toBe('male');
    expect(ASSISTANTS.LUMINA.gender).toBe('female');
  });
});
