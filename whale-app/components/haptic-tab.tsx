import { BottomTabBarButtonProps } from '@react-navigation/bottom-tabs';
import { PlatformPressable } from '@react-navigation/elements';
import * as Haptics from 'expo-haptics';
import { StyleSheet } from 'react-native';

export function HapticTab(props: BottomTabBarButtonProps) {
  const { style, onPressIn, ...rest } = props;

  return (
    <PlatformPressable
      {...rest}
      style={[style, styles.tabButton]}
      onPressIn={(ev) => {
        if (process.env.EXPO_OS === 'ios') {
          // Add a soft haptic feedback when pressing down on the tabs.
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }
        onPressIn?.(ev);
      }}
    />
  );
}

const styles = StyleSheet.create({
  tabButton: {
    height: 80,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 0,
    paddingBottom: 0,
  },
});
