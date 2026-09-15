import { Pressable, StyleSheet, ViewStyle } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { 
  primary, white, darkGray,
  FontSize, FontFamily 
} from '@/constants/theme';

type Props = {
  label: string;
  active: boolean;
  onPress?: () => void;
  style?: ViewStyle;
};

export function ThemedPillButton({ label, active, onPress, style }: Props) {
  return (
    <Pressable 
      onPress={onPress}
      style={[styles.base, active ? styles.active : styles.inactive, style]}
    >
      <ThemedText style={[
        styles.text, 
        active ? styles.activeText : styles.inactiveText,
      ]}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    width: 64,
    height: 32,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  active: {
    backgroundColor: primary,
  },
  inactive: {
    backgroundColor: 'transparent',
  },
  text: {
    fontSize: FontSize.xs,
    fontFamily: FontFamily.pretendardMedium,
  },
  activeText: { color: white },
  inactiveText: { color: darkGray },
});