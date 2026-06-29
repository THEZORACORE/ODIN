import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColors, Typography, Spacing } from '@/theme';

/** Placeholder — medicinmodulet bygges i Step 3. */
export default function MedicinScreen() {
  const colors = useColors();

  return (
    <SafeAreaView
      style={[styles.safe, { backgroundColor: colors.background }]}
      edges={['top']}
    >
      <View style={styles.container}>
        <Text style={[styles.title, { color: colors.text }]}>Medicin</Text>
        <Text style={[styles.body, { color: colors.textSecondary }]}>
          Her kan du tilføje medicin, doser og tidspunkter.{'\n'}
          Bygges i Step 3.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  container: {
    flex: 1,
    padding: Spacing.lg,
    paddingTop: Spacing.xxxl,
    gap: Spacing.md,
  },
  title: {
    fontSize: Typography.size.xl,
    fontWeight: Typography.weight.bold,
  },
  body: {
    fontSize: Typography.size.base,
    lineHeight: Typography.size.base * Typography.lineHeight.normal,
  },
});
