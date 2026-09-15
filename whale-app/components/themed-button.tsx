import { Pressable, StyleSheet, ViewStyle } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { 
  primary, white, lightGray, darkGray,
  FontSize, FontFamily 
} from '@/constants/theme';

type ButtonVariant = 'ghost' | 'light' | 'dark';

type Props = {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  style?: ViewStyle;
};

export function ThemedButton({ 
  label, 
  onPress, 
  variant = 'dark',
  style,
}: Props) {
  return (
    <Pressable 
      onPress={onPress} 
      style={[styles.base, styles[variant], style]}
    >
      <ThemedText style={[styles.text, textStyles[variant]]}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    width: 60,
    height: 30,
    borderRadius: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ghost: {
    backgroundColor: white,
  },
  light: {
    backgroundColor: lightGray,
  },
  dark: {
    backgroundColor: darkGray,
  },
  text: {
    fontSize: FontSize.base,  // 12
    fontFamily: FontFamily.pretendardMedium,
  },
});

const textStyles = StyleSheet.create({
  ghost: { color: darkGray },
  light: { color: darkGray },
  dark: { color: white },
});