import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';

/**
 * Rod-layout: wrapper for hele appen.
 * SafeAreaProvider håndterer notch og home-indicator på alle enheder.
 */
export default function RootLayout() {
  const scheme = useColorScheme();

  return (
    <SafeAreaProvider>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      {/* headerShown: false — hver skærm styrer selv sin header */}
      <Stack screenOptions={{ headerShown: false }} />
    </SafeAreaProvider>
  );
}
