import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AssistantHeader } from '@/components/AssistantHeader';
import { useColors, Typography, Spacing } from '@/theme';

/**
 * "I dag"-skærmen: brugerens daglige startpunkt.
 * Viser AssistantHeader øverst. Resten fyldes ud i Step 5 (dagsstruktur).
 */
export default function IDagScreen() {
  const colors = useColors();

  return (
    <SafeAreaView
      style={[styles.safe, { backgroundColor: colors.background }]}
      edges={['top']}
    >
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerSection}>
          <AssistantHeader />
        </View>

        {/* Placeholder — erstattes af dagsoversigt i Step 5 */}
        <View
          style={styles.placeholder}
          accessibilityRole="text"
        >
          <Text style={[styles.placeholderTitle, { color: colors.text }]}>
            God dag
          </Text>
          <Text style={[styles.placeholderBody, { color: colors.textSecondary }]}>
            Din dagsoversigt, opgaver og rutiner vises her når vi bygger Step 5.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
  },
  content: {
    padding: Spacing.lg,
    gap: Spacing.lg,
  },
  headerSection: {
    marginTop: Spacing.sm,
  },
  placeholder: {
    marginTop: Spacing.xxxl,
    alignItems: 'center',
    paddingHorizontal: Spacing.xxl,
    gap: Spacing.md,
  },
  placeholderTitle: {
    fontSize: Typography.size.xl,
    fontWeight: Typography.weight.semibold,
    textAlign: 'center',
  },
  placeholderBody: {
    fontSize: Typography.size.base,
    lineHeight: Typography.size.base * 1.5,
    textAlign: 'center',
  },
});
