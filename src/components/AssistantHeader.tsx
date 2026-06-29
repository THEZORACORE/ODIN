import React from 'react';
import { View, Text, StyleSheet, useColorScheme } from 'react-native';
import { ASSISTANTS } from '@/data/assistants';
import { useAssistantStore } from '@/store/assistantStore';
import { useColors, Typography, Spacing, Radius, Shadows } from '@/theme';

/**
 * Header-kort der viser den aktive assistent.
 * Placeres øverst på "I dag"-skærmen.
 * Accentfarven skifter automatisk med assistenten og farvetemaet.
 */
export function AssistantHeader() {
  const colors = useColors();
  const scheme = useColorScheme();
  const selectedId = useAssistantStore((s) => s.selectedAssistantId);
  const assistant = ASSISTANTS[selectedId];

  const accentColor =
    scheme === 'dark' ? assistant.accentColorDark : assistant.accentColor;

  return (
    <View
      style={[styles.container, { backgroundColor: colors.surface }, Shadows.sm]}
      accessibilityRole="header"
      accessibilityLabel={`Aktiv assistent: ${assistant.name}`}
    >
      {/* Farvet prik der indikerer hvilken assistent der er valgt */}
      <View
        style={[styles.dot, { backgroundColor: accentColor }]}
        accessibilityElementsHidden
        importantForAccessibility="no"
      />

      <View style={styles.textContainer}>
        <Text
          style={[styles.name, { color: accentColor }]}
          accessibilityRole="text"
        >
          {assistant.name.toUpperCase()}
        </Text>
        <Text
          style={[styles.description, { color: colors.textSecondary }]}
          numberOfLines={2}
        >
          {assistant.personalityDescription}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: Spacing.lg,
    paddingHorizontal: Spacing.xl,
    borderRadius: Radius.md,
    gap: Spacing.md,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: Radius.full,
    marginTop: 3, // Visuel justering til første tekstlinje
    flexShrink: 0,
  },
  textContainer: {
    flex: 1,
    gap: Spacing.xs,
  },
  name: {
    fontSize: Typography.size.xs,
    fontWeight: Typography.weight.bold,
    letterSpacing: 1.4,
  },
  description: {
    fontSize: Typography.size.sm,
    lineHeight: Typography.size.sm * Typography.lineHeight.normal,
  },
});
