/** Unik ID for hver assistent-personlighed. */
export type AssistantId = 'CONNOR' | 'LUMINA';

/** Biologisk køn — bruges til at tune sprogstil og grammatik. */
export type AssistantGender = 'male' | 'female';

/**
 * En komplet assistent-personlighed.
 * Alle felter er påkrævet — der findes ingen "halv" assistent.
 */
export interface Assistant {
  id: AssistantId;
  name: string;
  gender: AssistantGender;
  /** Én sætning der beskriver personligheden. */
  personalityDescription: string;
  /** Hvordan assistenten kommunikerer — rytme, ordvalg, energi. */
  toneOfVoice: string;
  /** Hex-farve til UI-accenter i lystilstand. */
  accentColor: string;
  /** Hex-farve til UI-accenter i mørktilstand (lysere for kontrast). */
  accentColorDark: string;
}
