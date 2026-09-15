import { Tabs } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { HapticTab } from '@/components/haptic-tab';
import { NavigationTabIcon } from '@/components/navigation-tab-icon';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const colors = Colors[colorScheme ?? 'light'];

  return (
    <Tabs
      initialRouteName="home"
      screenOptions={{
        tabBarActiveTintColor: colors.tabIconSelected,
        tabBarInactiveTintColor: colors.tabIconDefault,
        headerShown: false,
        tabBarButton: HapticTab,
        tabBarShowLabel: false,
        tabBarLabelStyle: styles.tabBarLabel,
        tabBarIconStyle: styles.tabBarIcon,
        tabBarItemStyle: styles.tabBarItem,
        tabBarStyle: styles.tabBar,
      }}>
      <Tabs.Screen
        name="home"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => (
            <View style={styles.tabBarIconOffset}>
              <NavigationTabIcon name="home" color={color} />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="write"
        options={{
          title: 'Write',
          tabBarIcon: ({ color }) => (
            <View style={styles.tabBarIconOffset}>
              <NavigationTabIcon name="write" color={color} />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="diary"
        options={{
          title: 'Diary',
          tabBarIcon: ({ color }) => (
            <View style={styles.tabBarIconOffset}>
              <NavigationTabIcon name="diary" color={color} />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color }) => (
            <View style={styles.tabBarIconOffset}>
              <NavigationTabIcon name="profile" color={color} />
            </View>
          ),
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    height: 80,
    paddingTop: 0,
    paddingBottom: 0,
    paddingHorizontal: 22
  },
  tabBarIcon: {
    flex: 0,
    marginTop: 0,
    marginBottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabBarIconOffset: {
    marginTop: -20,
  },
  tabBarItem: {
    flex: 1,
    height: '100%',
    padding: 0,
    paddingTop: 0,
    paddingBottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabBarLabel: {
    display: 'none',
  },
});
