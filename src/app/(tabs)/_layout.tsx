import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useColorScheme } from 'react-native';
import { ASSISTANTS } from '@/data/assistants';
import { useAssistantStore } from '@/store/assistantStore';
import { useColors, Typography, Spacing } from '@/theme';

type IoniconName = React.ComponentProps<typeof Ionicons>['name'];

interface TabConfig {
  name: string;
  title: string;
  iconOutline: IoniconName;
  iconFilled: IoniconName;
  a11yLabel: string; // tilgængeligheds-label til skærmlæser
}

const TABS: TabConfig[] = [
  {
    name: 'index',
    title: 'I dag',
    iconOutline: 'sunny-outline',
    iconFilled: 'sunny',
    a11yLabel: 'I dag — din dagsoversigt',
  },
  {
    name: 'medicin',
    title: 'Medicin',
    iconOutline: 'medical-outline',
    iconFilled: 'medical',
    a11yLabel: 'Medicin — påmindelser og log',
  },
  {
    name: 'fokus',
    title: 'Fokus',
    iconOutline: 'timer-outline',
    iconFilled: 'timer',
    a11yLabel: 'Fokus — timer og koncentrationsværktøjer',
  },
  {
    name: 'lyd',
    title: 'Lyd',
    iconOutline: 'musical-notes-outline',
    iconFilled: 'musical-notes',
    a11yLabel: 'Lyd — beroligende lyd og musik',
  },
];

/**
 * Tab-navigation: bundnavigation med fire sektioner.
 * Aktiv-farven matcher den valgte assistent og skifter automatisk.
 */
export default function TabLayout() {
  const colors = useColors();
  const scheme = useColorScheme();
  const selectedId = useAssistantStore((s) => s.selectedAssistantId);
  const assistant = ASSISTANTS[selectedId];

  const accentColor =
    scheme === 'dark' ? assistant.accentColorDark : assistant.accentColor;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: accentColor,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          paddingBottom: Spacing.xs,
          paddingTop: Spacing.xs,
          height: 60,
        },
        tabBarLabelStyle: {
          fontSize: Typography.size.xs,
          fontWeight: Typography.weight.medium,
          marginTop: 2,
        },
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarAccessibilityLabel: tab.a11yLabel,
            tabBarIcon: ({ focused, color, size }) => (
              <Ionicons
                name={focused ? tab.iconFilled : tab.iconOutline}
                size={size}
                color={color}
                // Ikoner er dekorative — skærmlæseren bruger tabBarAccessibilityLabel
                accessibilityElementsHidden
                importantForAccessibility="no"
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
